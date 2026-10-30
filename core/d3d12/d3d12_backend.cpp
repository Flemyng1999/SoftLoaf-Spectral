// Bounded compute transport. Algorithms and frozen colour tables live in shaders.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_6.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstring>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;
namespace {
thread_local std::string last_error;
void check(HRESULT result,const char* operation) {
    if(FAILED(result))throw std::runtime_error(std::string(operation)+" HRESULT="+std::to_string(static_cast<unsigned long>(result)));
}
struct Device {
    ComPtr<ID3D12Device> device;std::string name;
    Device() {
        ComPtr<IDXGIFactory6> factory;check(CreateDXGIFactory2(0,IID_PPV_ARGS(&factory)),"DXGI factory");
        for(UINT i=0;;++i){
            ComPtr<IDXGIAdapter1> adapter;
            if(factory->EnumAdapterByGpuPreference(i,DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE,IID_PPV_ARGS(&adapter))==DXGI_ERROR_NOT_FOUND)break;
            DXGI_ADAPTER_DESC1 desc{};adapter->GetDesc1(&desc);
            if(desc.Flags&DXGI_ADAPTER_FLAG_SOFTWARE)continue;
            if(SUCCEEDED(D3D12CreateDevice(adapter.Get(),D3D_FEATURE_LEVEL_11_0,IID_PPV_ARGS(&device)))){
                const int n=WideCharToMultiByte(CP_UTF8,0,desc.Description,-1,nullptr,0,nullptr,nullptr);
                std::vector<char> text(n);WideCharToMultiByte(CP_UTF8,0,desc.Description,-1,text.data(),n,nullptr,nullptr);name=text.data();return;
            }
        }
        throw std::runtime_error("No hardware D3D12 compute device; use the CPU backend.");
    }
};
// COM release during DLL_PROCESS_DETACH runs under the loader lock and may
// fast-fail in a display driver. Explicit shutdown occurs before DLL unloading.
std::mutex device_mutex;
Device* shared_device=nullptr;
std::atomic_uint active_programs=0;
Device& device(){std::lock_guard guard(device_mutex);if(!shared_device)shared_device=new Device;return *shared_device;}
struct Buffer {ComPtr<ID3D12Resource> resource;UINT64 capacity=0;};
void reserve(Buffer& buffer,UINT64 bytes,D3D12_HEAP_TYPE heap,D3D12_RESOURCE_STATES state,D3D12_RESOURCE_FLAGS flags=D3D12_RESOURCE_FLAG_NONE) {
    if(buffer.capacity>=bytes)return;
    D3D12_HEAP_PROPERTIES properties{};properties.Type=heap;
    D3D12_RESOURCE_DESC desc{};desc.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;desc.Width=std::max<UINT64>(bytes,4);desc.Height=1;desc.DepthOrArraySize=1;desc.MipLevels=1;desc.SampleDesc.Count=1;desc.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;desc.Flags=flags;
    buffer.resource.Reset();check(device().device->CreateCommittedResource(&properties,D3D12_HEAP_FLAG_NONE,&desc,state,nullptr,IID_PPV_ARGS(&buffer.resource)),"Compute buffer");buffer.capacity=desc.Width;
}
void upload(Buffer& buffer,const void* values,UINT64 bytes){void* target=nullptr;D3D12_RANGE empty{};check(buffer.resource->Map(0,&empty,&target),"Map upload");std::memcpy(target,values,static_cast<size_t>(bytes));buffer.resource->Unmap(0,nullptr);}
struct Texture {ComPtr<ID3D12Resource> resource;bool linear=true;UINT dimension=2;};
struct Program {
    ComPtr<ID3D12CommandQueue> queue;ComPtr<ID3D12CommandAllocator> allocator;
    ComPtr<ID3D12GraphicsCommandList> commands;ComPtr<ID3D12Fence> fence;
    ComPtr<ID3DBlob> shader;ComPtr<ID3D12RootSignature> root;ComPtr<ID3D12PipelineState> pipeline;
    ComPtr<ID3D12QueryHeap> timestamps;Buffer query_readback;UINT64 frequency=0;
    ComPtr<ID3D12DescriptorHeap> descriptors;
    std::array<Texture,16> textures;Buffer input,data,metadata,output,readback,texture_staging;
    UINT increment=0;UINT64 serial=0;HANDLE done=nullptr;bool copied=false,poisoned=false;
    std::mutex mutex;
    explicit Program(const char* source){
        auto* d=device().device.Get();ComPtr<ID3DBlob> errors;
        const auto result=D3DCompile(source,std::strlen(source),"softloaf-compute",nullptr,nullptr,"sl_pixels","cs_5_1",D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_OPTIMIZATION_LEVEL3,0,&shader,&errors);
        if(FAILED(result))throw std::runtime_error(errors?std::string(static_cast<const char*>(errors->GetBufferPointer()),errors->GetBufferSize()):"HLSL compilation failed");
        D3D12_COMMAND_QUEUE_DESC q{};q.Type=D3D12_COMMAND_LIST_TYPE_DIRECT;check(d->CreateCommandQueue(&q,IID_PPV_ARGS(&queue)),"Compute queue");
        check(d->CreateCommandAllocator(q.Type,IID_PPV_ARGS(&allocator)),"Compute allocator");
        check(d->CreateCommandList(0,q.Type,allocator.Get(),nullptr,IID_PPV_ARGS(&commands)),"Compute command list");check(commands->Close(),"Initial command close");
        check(d->CreateFence(0,D3D12_FENCE_FLAG_NONE,IID_PPV_ARGS(&fence)),"Compute fence");
        D3D12_DESCRIPTOR_HEAP_DESC h{};h.Type=D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;h.NumDescriptors=20;h.Flags=D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
        check(d->CreateDescriptorHeap(&h,IID_PPV_ARGS(&descriptors)),"Compute descriptor heap");increment=d->GetDescriptorHandleIncrementSize(h.Type);
        D3D12_QUERY_HEAP_DESC query{};query.Type=D3D12_QUERY_HEAP_TYPE_TIMESTAMP;query.Count=2;check(d->CreateQueryHeap(&query,IID_PPV_ARGS(&timestamps)),"GPU timestamps");
        check(queue->GetTimestampFrequency(&frequency),"GPU timestamp frequency");reserve(query_readback,16,D3D12_HEAP_TYPE_READBACK,D3D12_RESOURCE_STATE_COPY_DEST);
        done=CreateEventW(nullptr,FALSE,FALSE,nullptr);if(!done)throw std::runtime_error("Compute completion event failed");
        ++active_programs;
    }
    ~Program(){if(done)CloseHandle(done);--active_programs;}
    D3D12_CPU_DESCRIPTOR_HANDLE cpu(UINT index){auto h=descriptors->GetCPUDescriptorHandleForHeapStart();h.ptr+=static_cast<SIZE_T>(increment)*index;return h;}
    D3D12_GPU_DESCRIPTOR_HANDLE gpu(UINT index){auto h=descriptors->GetGPUDescriptorHandleForHeapStart();h.ptr+=static_cast<UINT64>(increment)*index;return h;}
    void begin(){if(poisoned)throw std::runtime_error("D3D12 context unavailable; use CPU");check(allocator->Reset(),"Allocator reset");check(commands->Reset(allocator.Get(),nullptr),"Command reset");}
    void submit(){
        check(commands->Close(),"Command close");ID3D12CommandList* lists[]={commands.Get()};poisoned=true;queue->ExecuteCommandLists(1,lists);
        check(queue->Signal(fence.Get(),++serial),"Compute signal");
        if(fence->GetCompletedValue()<serial){check(fence->SetEventOnCompletion(serial,done),"Fence completion");if(WaitForSingleObject(done,120000)!=WAIT_OBJECT_0){poisoned=true;throw std::runtime_error("D3D12 dispatch timeout; CPU fallback required");}}
        check(device().device->GetDeviceRemovedReason(),"D3D12 device status");
        poisoned=false;
    }
    void build(){
        if(pipeline)return;auto* d=device().device.Get();
        std::array<D3D12_DESCRIPTOR_RANGE,3> ranges{};
        ranges[0]={D3D12_DESCRIPTOR_RANGE_TYPE_SRV,3,0,1,0};ranges[1]={D3D12_DESCRIPTOR_RANGE_TYPE_UAV,1,0,1,0};ranges[2]={D3D12_DESCRIPTOR_RANGE_TYPE_SRV,16,0,0,0};
        std::array<D3D12_ROOT_PARAMETER,4> params{};
        for(UINT i: {0u,1u,3u}){params[i].ParameterType=D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;params[i].DescriptorTable={1,&ranges[i==3?2:i]};params[i].ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;}
        params[2].ParameterType=D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;params[2].Constants={0,1,1};params[2].ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;
        std::array<D3D12_STATIC_SAMPLER_DESC,16> samplers{};
        for(UINT i=0;i<16;++i){auto& s=samplers[i];s.Filter=textures[i].linear?D3D12_FILTER_MIN_MAG_MIP_LINEAR:D3D12_FILTER_MIN_MAG_MIP_POINT;s.AddressU=s.AddressV=s.AddressW=D3D12_TEXTURE_ADDRESS_MODE_CLAMP;s.MaxAnisotropy=1;s.ComparisonFunc=D3D12_COMPARISON_FUNC_NEVER;s.MaxLOD=D3D12_FLOAT32_MAX;s.ShaderRegister=i;s.ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;}
        D3D12_ROOT_SIGNATURE_DESC desc{};desc.NumParameters=static_cast<UINT>(params.size());desc.pParameters=params.data();desc.NumStaticSamplers=16;desc.pStaticSamplers=samplers.data();
        ComPtr<ID3DBlob> serialized,errors;check(D3D12SerializeRootSignature(&desc,D3D_ROOT_SIGNATURE_VERSION_1,&serialized,&errors),"Root signature serialization");
        check(d->CreateRootSignature(0,serialized->GetBufferPointer(),serialized->GetBufferSize(),IID_PPV_ARGS(&root)),"Root signature");
        D3D12_COMPUTE_PIPELINE_STATE_DESC p{};p.pRootSignature=root.Get();p.CS={shader->GetBufferPointer(),shader->GetBufferSize()};check(d->CreateComputePipelineState(&p,IID_PPV_ARGS(&pipeline)),"Compute pipeline");
        for(UINT i=0;i<16;++i){D3D12_SHADER_RESOURCE_VIEW_DESC s{};s.Format=DXGI_FORMAT_R32G32B32A32_FLOAT;s.Shader4ComponentMapping=D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
            s.ViewDimension=textures[i].dimension==1?D3D12_SRV_DIMENSION_TEXTURE1D:textures[i].dimension==3?D3D12_SRV_DIMENSION_TEXTURE3D:D3D12_SRV_DIMENSION_TEXTURE2D;
            if(s.ViewDimension==D3D12_SRV_DIMENSION_TEXTURE1D)s.Texture1D.MipLevels=1;else if(s.ViewDimension==D3D12_SRV_DIMENSION_TEXTURE3D)s.Texture3D.MipLevels=1;else s.Texture2D.MipLevels=1;
            d->CreateShaderResourceView(textures[i].resource.Get(),&s,cpu(4+i));}
    }
};
template<class F> int guarded(F body){try{last_error.clear();body();return 0;}catch(const std::exception& e){last_error=e.what();return 1;}catch(...){last_error="Unknown D3D12 failure";return 1;}}
void barrier(ID3D12GraphicsCommandList* c,ID3D12Resource* resource,D3D12_RESOURCE_STATES before,D3D12_RESOURCE_STATES after){D3D12_RESOURCE_BARRIER b{};b.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;b.Transition={resource,D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,before,after};c->ResourceBarrier(1,&b);}
}
#define API extern "C" __declspec(dllexport)
API const char* sl_d3d12_error(){return last_error.c_str();}
API int sl_d3d12_shutdown(){return guarded([]{std::lock_guard guard(device_mutex);if(active_programs)throw std::runtime_error("D3D12 programs are still active");delete shared_device;shared_device=nullptr;});}
API const char* sl_d3d12_device_name(){try{return device().name.c_str();}catch(const std::exception& e){last_error=e.what();return nullptr;}}
API void* sl_d3d12_create(const char* source){try{return source?new Program(source):nullptr;}catch(const std::exception& e){last_error=e.what();return nullptr;}}
API void sl_d3d12_destroy(void* handle){auto* p=static_cast<Program*>(handle);if(p&&p->poisoned&&p->fence->GetCompletedValue()<p->serial)return;delete p;}
API int sl_d3d12_texture(void* handle,UINT binding,UINT dimension,UINT width,UINT height,UINT depth,UINT channels,UINT linear,const float* values){return guarded([&]{
    auto* p=static_cast<Program*>(handle);if(!p||binding>=16||dimension<1||dimension>3||!width||!height||!depth||width>16384||height>16384||depth>2048||(channels!=1&&channels!=3)||!values||static_cast<UINT64>(width)*height*depth>16777216||p->pipeline)throw std::invalid_argument("Invalid frozen D3D12 texture");
    std::lock_guard guard(p->mutex);auto* d=device().device.Get();auto& texture=p->textures[binding];texture.dimension=dimension;texture.linear=linear!=0;
    D3D12_RESOURCE_DESC desc{};desc.Dimension=dimension==1?D3D12_RESOURCE_DIMENSION_TEXTURE1D:dimension==3?D3D12_RESOURCE_DIMENSION_TEXTURE3D:D3D12_RESOURCE_DIMENSION_TEXTURE2D;desc.Width=width;desc.Height=height;desc.DepthOrArraySize=static_cast<UINT16>(depth);desc.MipLevels=1;desc.Format=DXGI_FORMAT_R32G32B32A32_FLOAT;desc.SampleDesc.Count=1;
    D3D12_HEAP_PROPERTIES properties{};properties.Type=D3D12_HEAP_TYPE_DEFAULT;check(d->CreateCommittedResource(&properties,D3D12_HEAP_FLAG_NONE,&desc,D3D12_RESOURCE_STATE_COPY_DEST,nullptr,IID_PPV_ARGS(&texture.resource)),"OCIO texture");
    D3D12_PLACED_SUBRESOURCE_FOOTPRINT layout{};UINT rows=0;UINT64 rowBytes=0,total=0;d->GetCopyableFootprints(&desc,0,1,0,&layout,&rows,&rowBytes,&total);auto& staging=p->texture_staging;reserve(staging,total,D3D12_HEAP_TYPE_UPLOAD,D3D12_RESOURCE_STATE_GENERIC_READ);
    void* mapped=nullptr;D3D12_RANGE empty{};check(staging.resource->Map(0,&empty,&mapped),"Texture upload map");
    for(UINT z=0;z<depth;++z)for(UINT y=0;y<height;++y){auto* line=reinterpret_cast<float*>(static_cast<unsigned char*>(mapped)+layout.Offset+(static_cast<UINT64>(z)*rows+y)*layout.Footprint.RowPitch);for(UINT x=0;x<width;++x){const auto i=(static_cast<UINT64>(z)*height+y)*width+x;line[x*4]=values[i*channels];line[x*4+1]=channels==3?values[i*3+1]:0;line[x*4+2]=channels==3?values[i*3+2]:0;line[x*4+3]=1;}}
    staging.resource->Unmap(0,nullptr);p->begin();D3D12_TEXTURE_COPY_LOCATION from{},to{};from.pResource=staging.resource.Get();from.Type=D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;from.PlacedFootprint=layout;to.pResource=texture.resource.Get();to.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;p->commands->CopyTextureRegion(&to,0,0,0,&from,nullptr);barrier(p->commands.Get(),texture.resource.Get(),D3D12_RESOURCE_STATE_COPY_DEST,D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);p->submit();
});}
API int sl_d3d12_run(void* handle,const float* input,UINT64 pixels,UINT channels,const float* data,UINT64 dataCount,const UINT* metadata,UINT64 metadataCount,float* output,double* seconds){return guarded([&]{
    auto* p=static_cast<Program*>(handle);if(!p||!input||!data||!metadata||!output||!pixels||pixels>262144||!channels||channels>1024||pixels*channels>8*1048576||!dataCount||dataCount>8*1048576||!metadataCount||metadataCount>256)throw std::invalid_argument("Invalid bounded D3D12 dispatch");
    std::lock_guard guard(p->mutex);p->build();
    reserve(p->input,pixels*channels*4,D3D12_HEAP_TYPE_UPLOAD,D3D12_RESOURCE_STATE_GENERIC_READ);reserve(p->data,dataCount*4,D3D12_HEAP_TYPE_UPLOAD,D3D12_RESOURCE_STATE_GENERIC_READ);reserve(p->metadata,metadataCount*4,D3D12_HEAP_TYPE_UPLOAD,D3D12_RESOURCE_STATE_GENERIC_READ);
    const bool grow=p->output.capacity<pixels*12;reserve(p->output,pixels*12,D3D12_HEAP_TYPE_DEFAULT,D3D12_RESOURCE_STATE_UNORDERED_ACCESS,D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS);if(grow)p->copied=false;reserve(p->readback,pixels*12,D3D12_HEAP_TYPE_READBACK,D3D12_RESOURCE_STATE_COPY_DEST);
    upload(p->input,input,pixels*channels*4);upload(p->data,data,dataCount*4);upload(p->metadata,metadata,metadataCount*4);
    std::array<Buffer*,3> buffers={&p->input,&p->data,&p->metadata};const std::array<UINT64,3> counts={pixels*channels,dataCount,metadataCount};auto* d=device().device.Get();
    for(UINT i=0;i<3;++i){D3D12_SHADER_RESOURCE_VIEW_DESC v{};v.ViewDimension=D3D12_SRV_DIMENSION_BUFFER;v.Shader4ComponentMapping=D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;v.Buffer.NumElements=static_cast<UINT>(counts[i]);v.Buffer.StructureByteStride=4;d->CreateShaderResourceView(buffers[i]->resource.Get(),&v,p->cpu(i));}
    D3D12_UNORDERED_ACCESS_VIEW_DESC u{};u.ViewDimension=D3D12_UAV_DIMENSION_BUFFER;u.Buffer.NumElements=static_cast<UINT>(pixels*3);u.Buffer.StructureByteStride=4;d->CreateUnorderedAccessView(p->output.resource.Get(),nullptr,&u,p->cpu(3));
    p->begin();if(p->copied)barrier(p->commands.Get(),p->output.resource.Get(),D3D12_RESOURCE_STATE_COPY_SOURCE,D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
    ID3D12DescriptorHeap* heaps[]={p->descriptors.Get()};p->commands->SetDescriptorHeaps(1,heaps);p->commands->SetComputeRootSignature(p->root.Get());p->commands->SetPipelineState(p->pipeline.Get());p->commands->SetComputeRootDescriptorTable(0,p->gpu(0));p->commands->SetComputeRootDescriptorTable(1,p->gpu(3));p->commands->SetComputeRoot32BitConstant(2,static_cast<UINT>(pixels),0);p->commands->SetComputeRootDescriptorTable(3,p->gpu(4));p->commands->EndQuery(p->timestamps.Get(),D3D12_QUERY_TYPE_TIMESTAMP,0);p->commands->Dispatch(static_cast<UINT>((pixels+63)/64),1,1);p->commands->EndQuery(p->timestamps.Get(),D3D12_QUERY_TYPE_TIMESTAMP,1);p->commands->ResolveQueryData(p->timestamps.Get(),D3D12_QUERY_TYPE_TIMESTAMP,0,2,p->query_readback.resource.Get(),0);
    barrier(p->commands.Get(),p->output.resource.Get(),D3D12_RESOURCE_STATE_UNORDERED_ACCESS,D3D12_RESOURCE_STATE_COPY_SOURCE);p->copied=true;p->commands->CopyBufferRegion(p->readback.resource.Get(),0,p->output.resource.Get(),0,pixels*12);p->submit();
    void* result=nullptr;D3D12_RANGE range{0,static_cast<SIZE_T>(pixels*12)};check(p->readback.resource->Map(0,&range,&result),"Readback map");std::memcpy(output,result,static_cast<size_t>(pixels*12));D3D12_RANGE empty{};p->readback.resource->Unmap(0,&empty);
    if(seconds){void* ticks=nullptr;D3D12_RANGE time_range{0,16};check(p->query_readback.resource->Map(0,&time_range,&ticks),"Timestamp readback");const auto* values=static_cast<const UINT64*>(ticks);*seconds=static_cast<double>(values[1]-values[0])/p->frequency;p->query_readback.resource->Unmap(0,&empty);}
});}
