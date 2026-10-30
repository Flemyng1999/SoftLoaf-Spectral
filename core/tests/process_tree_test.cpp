#include "../../desktop/windows/process_tree.h"
#include <stdexcept>
int main(){
    const auto require=[](bool value){if(!value)throw std::runtime_error("service ownership mismatch");};
    const std::unordered_map<std::uint32_t,std::uint32_t> tree{{120,100},{140,120},{160,140},{200,50}};
    require(softloaf::belongs_to_launch(100,100,tree));
    require(softloaf::belongs_to_launch(140,100,tree));
    require(softloaf::belongs_to_launch(160,100,tree));
    require(!softloaf::belongs_to_launch(200,100,tree));
    require(!softloaf::belongs_to_launch(0,100,tree));
    require(!softloaf::belongs_to_launch(999,100,tree));
    require(!softloaf::belongs_to_launch(1,100,{{1,2},{2,1}}));
}
