// SPDX-License-Identifier: AGPL-3.0-only
// Independent native LibRaw half_size reference, before RT black/WB processing.
#include <libraw/libraw.h>
#include <omp.h>
#include <cstdio>
#include <cmath>
#ifndef LIBRAW_USE_OPENMP
#error LibRaw headers must agree with the OpenMP-enabled reentrant archive
#endif
int main(int argc,char**argv){
 if(argc!=2)return 2;
 libraw_data_t* raw=libraw_init(0);if(!raw)return 3;
 if(libraw_open_file(raw,argv[1])||libraw_unpack(raw)){libraw_close(raw);return 4;}
 const int width=raw->sizes.width,height=raw->sizes.height;
 const int top=raw->sizes.top_margin,left=raw->sizes.left_margin,pitch=raw->sizes.raw_pitch/2;
 // Use the public LibRaw half-size API, with no black/WB/RGB processing.
 raw->params.half_size=1;
 if(libraw_raw2image(raw)){libraw_close(raw);return 5;}
 if(raw->sizes.iwidth!=(width+1)/2||raw->sizes.iheight!=(height+1)/2){libraw_close(raw);return 6;}
 double maxError=0;
 for(int y=0;y+1<height;y+=2)for(int x=0;x+1<width;x+=2){
  double sum[3]={0,0,0};int count[3]={0,0,0};
  for(int dy=0;dy<2;dy++)for(int dx=0;dx<2;dx++){
   int c=libraw_COLOR(raw,y+dy,x+dx);if(c==3)c=1;
   sum[c]+=raw->rawdata.raw_image[(y+dy+top)*pitch+x+dx+left];count[c]++;
  }
  const auto& pixel=raw->image[(y/2)*raw->sizes.iwidth+x/2];
  const double out[3]={double(pixel[0]),.5*(pixel[1]+pixel[3]),double(pixel[2])};
  for(int c=0;c<3;c++)maxError=fmax(maxError,fabs(out[c]-sum[c]/count[c]));
 }
 std::printf("{\"LibRaw\":\"%s\",\"half_size\":1,\"OpenMP_max_threads\":%d,\"max_quartet_error\":%.10g,\"dimensions\":[%d,%d]}\n",libraw_version(),omp_get_max_threads(),maxError,raw->sizes.iwidth,raw->sizes.iheight);
 libraw_close(raw);return maxError==0?0:7;
}
