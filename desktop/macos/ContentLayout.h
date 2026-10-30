#pragma once
#import <Cocoa/Cocoa.h>

// The window guide positions a plain host; WebKit is constrained only to its
// immediate superview with an autoresizing mask; WebKit owns its compositor sizing.
static inline void SLInstallContentView(NSWindow *window, NSView *view) {
    if (!(window.styleMask & NSWindowStyleMaskFullSizeContentView)) {
        // A normal titled window already gives its content view the visible
        // rectangle. Direct hosting lets WebKit attach its drawing area once.
        view.translatesAutoresizingMaskIntoConstraints = YES;
        view.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
        window.contentView = view;
        return;
    }
    NSView *root = [[NSView alloc] initWithFrame:window.contentView.bounds];
    window.contentView = root;
    NSView *host = [[NSView alloc] initWithFrame:window.contentLayoutRect];
    host.translatesAutoresizingMaskIntoConstraints = NO;
    [root addSubview:host];
    NSLayoutGuide *visible = window.contentLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [host.leadingAnchor constraintEqualToAnchor:visible.leadingAnchor],
        [host.trailingAnchor constraintEqualToAnchor:visible.trailingAnchor],
        [host.topAnchor constraintEqualToAnchor:visible.topAnchor],
        [host.bottomAnchor constraintEqualToAnchor:visible.bottomAnchor]
    ]];
    view.translatesAutoresizingMaskIntoConstraints = YES;
    view.frame = host.bounds;
    view.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    [host addSubview:view];
    [root layoutSubtreeIfNeeded];
}
