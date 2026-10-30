// Independent Metal execution bridge. Pixel mathematics lives in spectral.metal.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

#define EXPORT extern "C" __attribute__((visibility("default")))
namespace {
thread_local std::string last_error;
struct Program {
    id<MTLDevice> device;
    id<MTLCommandQueue> queue;
    id<MTLComputePipelineState> pipeline;
    id<MTLBuffer> input, output, data, metadata, count;
    std::vector<id<MTLTexture>> textures;
    std::vector<id<MTLSamplerState>> samplers;
    std::mutex mutex;
};
int fail(const char *message) { last_error=message; return 1; }
bool reserve(id<MTLDevice> device,id<MTLBuffer> __strong &buffer,NSUInteger bytes) {
    if (!buffer || buffer.length<bytes || buffer.length>std::max<NSUInteger>(bytes*4,16*1024*1024)) buffer=[device newBufferWithLength:std::max<NSUInteger>(bytes,16) options:MTLResourceStorageModeShared];
    return buffer!=nil;
}
}

EXPORT const char *sl_metal_error() { return last_error.c_str(); }
EXPORT const char *sl_metal_device_name() {
    @autoreleasepool { id<MTLDevice> device=MTLCreateSystemDefaultDevice();
        static std::string name; if(device)name=device.name.UTF8String; return device?name.c_str():nullptr; }
}
EXPORT void *sl_metal_create(const char *source) {
    @autoreleasepool {
        id<MTLDevice> device=MTLCreateSystemDefaultDevice();
        if(!device){fail("No Metal device; CPU reference must be explicitly selected.");return nullptr;}
        MTLCompileOptions *options=[MTLCompileOptions new];options.fastMathEnabled=NO;options.languageVersion=MTLLanguageVersion2_0;
        NSError *error=nil;
        id<MTLLibrary> library=[device newLibraryWithSource:[NSString stringWithUTF8String:source] options:options error:&error];
        if(!library){last_error=error.localizedDescription.UTF8String;return nullptr;}
        id<MTLFunction> function=[library newFunctionWithName:@"sl_pixels"];
        if(!function){fail("Missing sl_pixels Metal kernel.");return nullptr;}
        id<MTLComputePipelineState> pipeline=[device newComputePipelineStateWithFunction:function error:&error];
        if(!pipeline){last_error=error.localizedDescription.UTF8String;return nullptr;}
        auto *p=new Program;p->device=device;p->queue=[device newCommandQueue];p->pipeline=pipeline;
        p->textures.resize(32);p->samplers.resize(32);
        return p;
    }
}
EXPORT void sl_metal_destroy(void *pointer) { delete static_cast<Program*>(pointer); }

EXPORT int sl_metal_texture(void *pointer,uint32_t binding,uint32_t dimension,uint32_t width,uint32_t height,uint32_t depth,uint32_t channels,uint32_t linear,const float *values) {
    @autoreleasepool {
        auto *p=static_cast<Program*>(pointer);
        if(!p||binding>=32||dimension<1||dimension>3||width==0||height==0||depth==0||(channels!=1&&channels!=3)||!values)return fail("Invalid OCIO Metal texture.");
        std::lock_guard<std::mutex> lock(p->mutex);
        MTLTextureDescriptor *desc=[MTLTextureDescriptor new];
        desc.textureType=dimension==3?MTLTextureType3D:dimension==2?MTLTextureType2D:MTLTextureType1D;
        desc.width=width;desc.height=height;desc.depth=depth;
        desc.pixelFormat=channels==1?MTLPixelFormatR32Float:MTLPixelFormatRGBA32Float;
        desc.storageMode=MTLStorageModeShared;desc.usage=MTLTextureUsageShaderRead;
        id<MTLTexture> texture=[p->device newTextureWithDescriptor:desc];
        if(!texture)return fail("Metal texture allocation failed.");
        size_t pixels=static_cast<size_t>(width)*height*depth;
        std::vector<float> rgba;
        const float *upload=values;
        if(channels==3){rgba.resize(pixels*4);for(size_t i=0;i<pixels;i++){std::memcpy(rgba.data()+i*4,values+i*3,3*sizeof(float));rgba[i*4+3]=1;}upload=rgba.data();}
        NSUInteger components=channels==1?1:4;
        [texture replaceRegion:MTLRegionMake3D(0,0,0,width,height,depth) mipmapLevel:0 slice:0 withBytes:upload bytesPerRow:width*components*sizeof(float) bytesPerImage:width*height*components*sizeof(float)];
        MTLSamplerDescriptor *sampler=[MTLSamplerDescriptor new];
        sampler.minFilter=linear?MTLSamplerMinMagFilterLinear:MTLSamplerMinMagFilterNearest;sampler.magFilter=sampler.minFilter;
        sampler.sAddressMode=MTLSamplerAddressModeClampToEdge;sampler.tAddressMode=MTLSamplerAddressModeClampToEdge;sampler.rAddressMode=MTLSamplerAddressModeClampToEdge;
        p->textures[binding]=texture;p->samplers[binding]=[p->device newSamplerStateWithDescriptor:sampler];return 0;
    }
}

EXPORT int sl_metal_run(void *pointer,const float *input,uint64_t pixels,uint32_t channels,const float *data,uint64_t data_count,const uint32_t *metadata,uint64_t metadata_count,float *output,double *gpu_seconds) {
    @autoreleasepool {
        auto *p=static_cast<Program*>(pointer);
        if(!p||!input||!data||!metadata||!output||pixels==0||pixels>262144||channels==0||channels>1024||data_count>8*1048576||metadata_count>256)return fail("Invalid bounded Metal dispatch.");
        std::lock_guard<std::mutex> lock(p->mutex);
        if(!reserve(p->device,p->input,pixels*channels*sizeof(float))||!reserve(p->device,p->output,pixels*3*sizeof(float))||!reserve(p->device,p->data,data_count*sizeof(float))||!reserve(p->device,p->metadata,metadata_count*sizeof(uint32_t))||!reserve(p->device,p->count,sizeof(uint32_t)))return fail("Metal buffer allocation failed.");
        std::memcpy(p->input.contents,input,pixels*channels*sizeof(float));std::memcpy(p->data.contents,data,data_count*sizeof(float));std::memcpy(p->metadata.contents,metadata,metadata_count*sizeof(uint32_t));
        *static_cast<uint32_t*>(p->count.contents)=static_cast<uint32_t>(pixels);
        id<MTLCommandBuffer> command=[p->queue commandBuffer];command.label=@"SoftLoaf fused spectral pixels";
        id<MTLComputeCommandEncoder> encoder=[command computeCommandEncoder];
        [encoder setComputePipelineState:p->pipeline];
        [encoder setBuffer:p->input offset:0 atIndex:0];[encoder setBuffer:p->data offset:0 atIndex:1];[encoder setBuffer:p->metadata offset:0 atIndex:2];[encoder setBuffer:p->output offset:0 atIndex:3];[encoder setBuffer:p->count offset:0 atIndex:4];
        for(NSUInteger i=0;i<p->textures.size();i++)if(p->textures[i]){[encoder setTexture:p->textures[i] atIndex:i];[encoder setSamplerState:p->samplers[i] atIndex:i];}
        NSUInteger group=std::min<NSUInteger>(128,p->pipeline.maxTotalThreadsPerThreadgroup);
        group=std::max<NSUInteger>(p->pipeline.threadExecutionWidth,(group/p->pipeline.threadExecutionWidth)*p->pipeline.threadExecutionWidth);
        [encoder dispatchThreads:MTLSizeMake(pixels,1,1) threadsPerThreadgroup:MTLSizeMake(group,1,1)];[encoder endEncoding];
        [command commit];[command waitUntilCompleted];
        if(command.status!=MTLCommandBufferStatusCompleted){last_error=command.error.localizedDescription.UTF8String;return 1;}
        std::memcpy(output,p->output.contents,pixels*3*sizeof(float));
        if(gpu_seconds)*gpu_seconds=command.GPUEndTime-command.GPUStartTime;
        return 0;
    }
}
