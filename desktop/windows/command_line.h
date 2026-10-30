#pragma once
#include <string>

namespace softloaf {
// Quote one argument for the Windows CRT parser, including a trailing backslash.
inline std::wstring quote_argument(const std::wstring& value) {
    std::wstring output=L"\"";std::size_t slashes=0;
    for(const auto c:value) {
        if(c==L'\\'){++slashes;continue;}
        if(c==L'\"'){output.append(slashes*2+1,L'\\');output+=c;}
        else{output.append(slashes,L'\\');output+=c;}
        slashes=0;
    }
    output.append(slashes*2,L'\\');output+=L'\"';return output;
}
}
