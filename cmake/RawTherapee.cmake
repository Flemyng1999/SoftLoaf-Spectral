# Build the pinned vendored CLI in its own CMake project to isolate upstream flags.
option(SOFTLOAF_RAWTHERAPEE "Build the source-integrated RAW engine" ${APPLE})
if(NOT SOFTLOAF_RAWTHERAPEE)
    return()
endif()
include(ExternalProject)
set(SOFTLOAF_RT_SOURCE "${CMAKE_SOURCE_DIR}/third_party/rawtherapee")
set(SOFTLOAF_RT_RUNTIME "${CMAKE_SOURCE_DIR}/local/runtime/RawTherapeeEngine.app/Contents")
set(SOFTLOAF_RT_FLAGS
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_BUILD_TYPE=Release
    -DOPTION_OMP=ON -DPROC_TARGET_NUMBER=2 -DWITH_JXL=OFF
    -DCMAKE_OSX_DEPLOYMENT_TARGET=${CMAKE_OSX_DEPLOYMENT_TARGET})
if(APPLE)
    find_path(SOFTLOAF_OMP_INCLUDE omp.h HINTS /opt/homebrew/opt/libomp/include /usr/local/opt/libomp/include REQUIRED)
    find_library(SOFTLOAF_OMP_LIBRARY omp HINTS /opt/homebrew/opt/libomp/lib /usr/local/opt/libomp/lib REQUIRED)
    if(EXISTS /opt/homebrew)
        list(APPEND SOFTLOAF_RT_FLAGS -DLOCAL_PREFIX=/opt/homebrew)
    else()
        list(APPEND SOFTLOAF_RT_FLAGS -DLOCAL_PREFIX=/usr/local)
    endif()
    list(APPEND SOFTLOAF_RT_FLAGS
        "-DOpenMP_C_FLAGS=-Xclang -fopenmp -I${SOFTLOAF_OMP_INCLUDE}"
        "-DOpenMP_CXX_FLAGS=-Xclang -fopenmp -I${SOFTLOAF_OMP_INCLUDE}"
        -DOpenMP_C_LIB_NAMES=omp -DOpenMP_CXX_LIB_NAMES=omp
        -DOpenMP_omp_LIBRARY=${SOFTLOAF_OMP_LIBRARY})
endif()
ExternalProject_Add(softloaf_rawtherapee_cli
    SOURCE_DIR "${SOFTLOAF_RT_SOURCE}"
    BINARY_DIR "${CMAKE_BINARY_DIR}/rawtherapee"
    DOWNLOAD_COMMAND "" UPDATE_COMMAND ""
    CMAKE_ARGS ${SOFTLOAF_RT_FLAGS}
    BUILD_COMMAND ${CMAKE_COMMAND} --build <BINARY_DIR> --target rth-cli --parallel 4
    BUILD_ALWAYS TRUE
    INSTALL_COMMAND ${CMAKE_COMMAND} -E make_directory "${SOFTLOAF_RT_RUNTIME}/MacOS"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different <BINARY_DIR>/rtgui/rawtherapee-cli "${SOFTLOAF_RT_RUNTIME}/MacOS/rawtherapee-cli"
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${SOFTLOAF_RT_SOURCE}/rtdata" "${SOFTLOAF_RT_RUNTIME}/Resources/share"
    BUILD_BYPRODUCTS "${SOFTLOAF_RT_RUNTIME}/MacOS/rawtherapee-cli")
