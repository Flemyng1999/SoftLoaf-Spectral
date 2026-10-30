// Original SoftLoaf Spectral row I/O. libpng retains its own license.
#include <png.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <new>
#include <limits>
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <string>
#endif

#if defined(_WIN32)
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif
namespace {
FILE* open_utf8(const char* path,bool write) {
#if defined(_WIN32)
    const int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,nullptr,0);
    if(!size)return nullptr;
    std::wstring wide(static_cast<size_t>(size),L'\0');
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,wide.data(),size))return nullptr;
    return _wfopen(wide.c_str(),write?L"wb":L"rb");
#else
    return std::fopen(path,write?"wb":"rb");
#endif
}
thread_local char last_error[512] = {};
struct Stream {
    FILE* file=nullptr;
    png_structp png=nullptr;
    png_infop info=nullptr;
    std::uint32_t width=0,height=0,row=0;
    bool write=false,finished=false,failed=false;
};
void fail(png_structp png,png_const_charp message) {
    std::snprintf(last_error,sizeof(last_error),"%s",message?message:"PNG error");
    auto* s=static_cast<Stream*>(png_get_error_ptr(png));
    if(s)s->failed=true;
    png_longjmp(png,1);
}
void warning(png_structp,png_const_charp) {}
void close(Stream* s) {
    if(!s)return;
    if(s->png){
        if(s->write)png_destroy_write_struct(&s->png,&s->info);
        else png_destroy_read_struct(&s->png,&s->info,nullptr);
    }
    if(s->file)std::fclose(s->file);
    delete s;
}
bool valid_size(std::uint32_t w,std::uint32_t h) {
    return w>0&&h>0&&w<=16777216&&h<=16777216&&std::uint64_t(w)*3<std::numeric_limits<std::size_t>::max();
}
}
API const char* sl_png_error(){return last_error;}
API void sl_png_close(void* handle){close(static_cast<Stream*>(handle));}
API void* sl_png_writer_open(const char* path,std::uint32_t width,std::uint32_t height,
                            const unsigned char* icc,std::uint32_t icc_size,
                            const char* fingerprint,int compression) {
    last_error[0]=0;
    if(!path||!valid_size(width,height)||!icc||icc_size==0||icc_size>4*1024*1024||compression<0||compression>9){
        std::snprintf(last_error,sizeof(last_error),"Invalid PNG writer arguments");return nullptr;
    }
    auto* s=new(std::nothrow) Stream;
    if(!s)return nullptr;
    s->write=true;s->width=width;s->height=height;s->file=open_utf8(path,true);
    if(!s->file){std::snprintf(last_error,sizeof(last_error),"Could not open PNG output");close(s);return nullptr;}
    s->png=png_create_write_struct(PNG_LIBPNG_VER_STRING,s,fail,warning);
    if(!s->png){close(s);return nullptr;}
    s->info=png_create_info_struct(s->png);
    if(!s->info){close(s);return nullptr;}
    if(setjmp(png_jmpbuf(s->png))){close(s);return nullptr;}
    png_init_io(s->png,s->file);
    png_set_compression_level(s->png,compression);
    png_set_IHDR(s->png,s->info,width,height,8,PNG_COLOR_TYPE_RGB,
                 PNG_INTERLACE_NONE,PNG_COMPRESSION_TYPE_DEFAULT,PNG_FILTER_TYPE_DEFAULT);
    png_set_iCCP(s->png,s->info,"SoftLoaf Spectral",PNG_COMPRESSION_TYPE_BASE,icc,icc_size);
    if(fingerprint&&*fingerprint){
        png_text text{};text.compression=PNG_TEXT_COMPRESSION_NONE;
        text.key=const_cast<char*>("SoftLoaf recipe fingerprint");text.text=const_cast<char*>(fingerprint);
        png_set_text(s->png,s->info,&text,1);
    }
    png_write_info(s->png,s->info);
    return s;
}
API int sl_png_write(void* handle,const unsigned char* data,std::uint32_t rows,std::uint64_t stride) {
    auto* s=static_cast<Stream*>(handle);
    if(!s||!s->write||s->finished||s->failed||!data||rows==0||rows>s->height-s->row||stride<std::uint64_t(s->width)*3)return 1;
    if(setjmp(png_jmpbuf(s->png)))return 1;
    for(std::uint32_t i=0;i<rows;++i)png_write_row(s->png,const_cast<png_bytep>(data+i*stride));
    s->row+=rows;return 0;
}
API int sl_png_finish(void* handle) {
    auto* s=static_cast<Stream*>(handle);
    if(!s||s->failed||s->row!=s->height)return 1;
    if(s->finished)return 0;
    if(setjmp(png_jmpbuf(s->png)))return 1;
    if(s->write){png_write_end(s->png,s->info);if(std::fflush(s->file)!=0){s->failed=true;return 1;}}
    else png_read_end(s->png,s->info);
    s->finished=true;return 0;
}
API void* sl_png_reader_open(const char* path) {
    last_error[0]=0;
    auto* s=new(std::nothrow) Stream;
    if(!s)return nullptr;
    s->file=open_utf8(path,false);
    if(!s->file){std::snprintf(last_error,sizeof(last_error),"Could not open PNG input");close(s);return nullptr;}
    s->png=png_create_read_struct(PNG_LIBPNG_VER_STRING,s,fail,warning);
    if(!s->png){close(s);return nullptr;}
    s->info=png_create_info_struct(s->png);
    if(!s->info){close(s);return nullptr;}
    if(setjmp(png_jmpbuf(s->png))){close(s);return nullptr;}
    png_set_user_limits(s->png,16777216,16777216);
    png_set_crc_action(s->png,PNG_CRC_ERROR_QUIT,PNG_CRC_ERROR_QUIT);
    png_init_io(s->png,s->file);png_read_info(s->png,s->info);
    s->width=png_get_image_width(s->png,s->info);s->height=png_get_image_height(s->png,s->info);
    if(!valid_size(s->width,s->height)||png_get_bit_depth(s->png,s->info)!=8||
       png_get_color_type(s->png,s->info)!=PNG_COLOR_TYPE_RGB||png_get_interlace_type(s->png,s->info)!=PNG_INTERLACE_NONE){
        std::snprintf(last_error,sizeof(last_error),"Expected noninterlaced RGB8 PNG");close(s);return nullptr;
    }
    png_read_update_info(s->png,s->info);
    return s;
}
API std::uint32_t sl_png_width(void* handle){return static_cast<Stream*>(handle)->width;}
API std::uint32_t sl_png_height(void* handle){return static_cast<Stream*>(handle)->height;}
API const unsigned char* sl_png_icc(void* handle,std::uint32_t* size){
    auto* s=static_cast<Stream*>(handle);png_charp name=nullptr;int compression=0;png_bytep profile=nullptr;png_uint_32 length=0;
    png_get_iCCP(s->png,s->info,&name,&compression,&profile,&length);*size=length;return profile;
}
API const char* sl_png_fingerprint(void* handle){
    auto* s=static_cast<Stream*>(handle);png_textp text=nullptr;int count=0;
    png_get_text(s->png,s->info,&text,&count);
    for(int i=0;i<count;++i)if(std::strcmp(text[i].key,"SoftLoaf recipe fingerprint")==0)return text[i].text;
    return "";
}
API int sl_png_read(void* handle,unsigned char* output,std::uint32_t rows,std::uint64_t stride){
    auto* s=static_cast<Stream*>(handle);
    if(!s||s->write||s->failed||s->finished||!output||rows==0||rows>s->height-s->row||stride<std::uint64_t(s->width)*3)return 1;
    if(setjmp(png_jmpbuf(s->png)))return 1;
    for(std::uint32_t i=0;i<rows;++i)png_read_row(s->png,output+i*stride,nullptr);
    s->row+=rows;return 0;
}
