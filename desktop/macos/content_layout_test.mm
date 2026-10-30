#import <Cocoa/Cocoa.h>
#import "ContentLayout.h"
#include <cmath>
#include <iostream>

int main() {
    @autoreleasepool {
        [NSApplication sharedApplication];
        for (NSWindowStyleMask extra : {NSWindowStyleMask(0), NSWindowStyleMask(NSWindowStyleMaskFullSizeContentView)}) {
            NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,960,650)
                styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskResizable | extra
                backing:NSBackingStoreBuffered defer:NO];
            NSView *content = [NSView new];
            SLInstallContentView(window,content);
            NSRect initial = [content convertRect:content.bounds toView:nil];
            if (NSWidth(initial)<900 || NSHeight(initial)<600) {
                std::cerr << "Initial content has no visible size: " << NSStringFromRect(initial).UTF8String << '\n';
                return 1;
            }
            for (NSSize size : {NSMakeSize(960,650),NSMakeSize(1320,850),NSMakeSize(1100,680)}) {
                [window setContentSize:size];
                [window.contentView layoutSubtreeIfNeeded];
                NSRect actual = [content convertRect:content.bounds toView:nil];
                NSRect visible = window.contentLayoutRect;
                if (std::abs(NSMinY(actual)-NSMinY(visible)) > .5 ||
                    std::abs(NSMaxY(actual)-NSMaxY(visible)) > .5 ||
                    std::abs(NSWidth(actual)-NSWidth(visible)) > .5) {
                    std::cerr << "Content extends behind titlebar or outside visible window: "
                        << NSStringFromRect(actual).UTF8String << " vs "
                        << NSStringFromRect(visible).UTF8String << '\n';
                    return 1;
                }
            }
        }
    }
    return 0;
}
