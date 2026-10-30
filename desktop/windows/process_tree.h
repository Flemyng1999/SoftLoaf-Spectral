#pragma once
#include <cstdint>
#include <unordered_map>
#include <unordered_set>

namespace softloaf {
// Windows venv launchers may delegate to a child python.exe. Accept only a
// live snapshot's launch process or descendant; bound corrupt/cyclic chains.
inline bool belongs_to_launch(std::uint32_t candidate,std::uint32_t launcher,
    const std::unordered_map<std::uint32_t,std::uint32_t>& parents){
    std::unordered_set<std::uint32_t> visited;
    for(unsigned depth=0;candidate&&launcher&&depth<64;++depth){
        if(candidate==launcher)return true;
        if(!visited.insert(candidate).second)return false;
        const auto entry=parents.find(candidate);
        if(entry==parents.end())return false;
        candidate=entry->second;
    }
    return false;
}
}
