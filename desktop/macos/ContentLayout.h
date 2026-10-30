#pragma once
#import <Cocoa/Cocoa.h>

// Install application content in the window. Kept separate from service startup
// so titlebar geometry can be checked without loading materials or running HTTP.
static inline void SLInstallContentView(NSWindow *window, NSView *view) {
    NSView *root = [[NSView alloc] initWithFrame:window.contentView.bounds];
    window.contentView = root;
    view.translatesAutoresizingMaskIntoConstraints = NO;
    [root addSubview:view];
    NSLayoutGuide *visible = window.contentLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [view.leadingAnchor constraintEqualToAnchor:visible.leadingAnchor],
        [view.trailingAnchor constraintEqualToAnchor:visible.trailingAnchor],
        [view.topAnchor constraintEqualToAnchor:visible.topAnchor],
        [view.bottomAnchor constraintEqualToAnchor:visible.bottomAnchor]
    ]];
    [root layoutSubtreeIfNeeded];
}
