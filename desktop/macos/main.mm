#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>
#import "ContentLayout.h"
#include <unistd.h>

@interface SpectralApp : NSObject <NSApplicationDelegate, NSWindowDelegate,
    WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, WKScriptMessageHandler>
@property NSWindow *window;
@property WKWebView *web;
@property NSTask *service;
@property NSTimer *readiness;
@property NSURL *baseURL;
@property NSString *readyFile;
@property NSDate *started;
@property NSMutableSet<WKDownload *> *downloads;
@property BOOL quitting;
@property NSTextField *loading;
@property BOOL refreshedDrawingArea;
@end

@implementation SpectralApp
- (void)failure:(NSString *)message {
    NSAlert *alert = [NSAlert new];
    alert.messageText = @"面包光谱无法启动";
    alert.informativeText = message;
    [alert addButtonWithTitle:@"关闭"];
    [alert runModal];
    [NSApp terminate:nil];
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    NSMenu *menu = [NSMenu new];
    NSMenuItem *applicationItem = [NSMenuItem new];
    NSMenu *applicationMenu = [NSMenu new];
    [applicationMenu addItemWithTitle:@"关于面包光谱" action:@selector(showAbout:) keyEquivalent:@""];
    [applicationMenu addItem:[NSMenuItem separatorItem]];
    [applicationMenu itemAtIndex:0].target = self;
    NSMenuItem *settingsItem = [applicationMenu addItemWithTitle:@"设置…" action:@selector(openSettings:) keyEquivalent:@","];
    settingsItem.target = self;
    [applicationMenu addItem:[NSMenuItem separatorItem]];
    [applicationMenu addItemWithTitle:@"退出面包光谱" action:@selector(terminate:) keyEquivalent:@"q"];
    applicationItem.submenu = applicationMenu; [menu addItem:applicationItem];
    NSMenuItem *editItem = [NSMenuItem new];
    NSMenu *edit = [[NSMenu alloc] initWithTitle:@"编辑"];
    [edit addItemWithTitle:@"剪切" action:@selector(cut:) keyEquivalent:@"x"];
    [edit addItemWithTitle:@"复制" action:@selector(copy:) keyEquivalent:@"c"];
    [edit addItemWithTitle:@"粘贴" action:@selector(paste:) keyEquivalent:@"v"];
    [edit addItemWithTitle:@"全选" action:@selector(selectAll:) keyEquivalent:@"a"];
    editItem.submenu = edit; [menu addItem:editItem]; NSApp.mainMenu = menu;
    self.downloads = [NSMutableSet new];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1320, 850)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                  NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"面包光谱";
    self.window.minSize = NSMakeSize(960, 650);
    self.window.delegate = self;
    NSTextField *loading = [NSTextField labelWithString:@"正在载入光谱材料与计算内核…"];
    loading.frame = NSMakeRect(40, 400, 800, 30);
    self.loading = loading;
    [self.window.contentView addSubview:loading];
    [self.window center]; [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
    [self startService];
}
- (NSDictionary *)serviceEnvironment {
    NSMutableDictionary *environment = [NSProcessInfo.processInfo.environment mutableCopy];
    for (NSString *name in @[@"PYTHONPATH",@"PYTHONHOME",@"PYTHONSTARTUP",@"DYLD_LIBRARY_PATH",@"DYLD_FRAMEWORK_PATH"])
        [environment removeObjectForKey:name];
    return environment;
}
- (BOOL)configureService:(NSString *)executable state:(NSString *)state {
    NSTask *probe = [NSTask new]; probe.executableURL = [NSURL fileURLWithPath:executable];
    probe.arguments = @[@"--needs-setup"]; probe.environment = [self serviceEnvironment];
    NSError *error = nil;
    if (![probe launchAndReturnError:&error]) return NO;
    [probe waitUntilExit];
    if (probe.terminationStatus == 0) return YES;
    NSOpenPanel *science = [NSOpenPanel openPanel];
    science.canChooseFiles = NO; science.canChooseDirectories = YES; science.allowsMultipleSelection = NO;
    science.message = @"选择光谱资料文件夹（含 runtime-science.json）";
    science.prompt = @"选择资料";
    if ([science runModal] != NSModalResponseOK) return NO;
    NSOpenPanel *data = [NSOpenPanel openPanel];
    data.canChooseFiles = NO; data.canChooseDirectories = YES; data.allowsMultipleSelection = NO;
    data.message = @"选择外置数据盘上的文件夹，用于 RAW、预览和缓存。";
    data.prompt = @"选择数据位置"; data.directoryURL = [NSURL fileURLWithPath:@"/Volumes"];
    if ([data runModal] != NSModalResponseOK) return NO;
    NSURL *volume = nil; [data.URL getResourceValue:&volume forKey:NSURLVolumeURLKey error:nil];
    if (!volume) return NO;
    NSString *pixels = data.URL.path;
    NSTask *configure = [NSTask new]; configure.executableURL = [NSURL fileURLWithPath:executable];
    configure.arguments = @[@"--configure",@"--science-root",science.URL.path,@"--data-root",pixels,@"--volume",volume.path];
    configure.currentDirectoryURL = [NSURL fileURLWithPath:state];
    configure.environment = [self serviceEnvironment];
    NSPipe *output = [NSPipe pipe];configure.standardOutput = output;configure.standardError = output;
    if (![configure launchAndReturnError:&error]) return NO;
    NSData *response = [output.fileHandleForReading readDataToEndOfFile];[configure waitUntilExit];
    if (configure.terminationStatus == 0) return YES;
    NSDictionary *record = [NSJSONSerialization JSONObjectWithData:response options:0 error:nil];
    NSAlert *alert = [NSAlert new];alert.messageText = @"无法使用这份资料或数据位置";
    alert.informativeText = record[@"message"] ?: @"请选择完整的光谱资料，并确认外置数据盘已经连接。";
    [alert runModal];return NO;
}
- (void)startService {
    NSString *resource = NSBundle.mainBundle.resourcePath;
#if SOFTLOAF_PACKAGED_SERVICE
    NSString *state = NSProcessInfo.processInfo.environment[@"SOFTLOAF_STATE_HOME"];
    if (!state) state = [[NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory,NSUserDomainMask,YES) firstObject]
        stringByAppendingPathComponent:@"SoftLoafSpectral"];
    [[NSFileManager defaultManager] createDirectoryAtPath:state withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *checkout = state;
    NSString *python = [resource stringByAppendingPathComponent:@"Service/spectral-service"];
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:python]) {
        [self failure:@"安装包缺少计算服务，请重新安装面包光谱。"];
        return;
    }
    if (![self configureService:python state:state]) { [NSApp terminate:nil]; return; }
#else
    NSDictionary *runtime = [NSDictionary dictionaryWithContentsOfFile:[resource stringByAppendingPathComponent:@"runtime.plist"]];
    NSString *checkout = runtime[@"Checkout"], *python = runtime[@"Python"];
    if (!checkout || !python || ![[NSFileManager defaultManager] isExecutableFileAtPath:python]) {
        [self failure:@"这是本地开发版，需要构建时指定的 Python 环境。请按照开发说明重新构建。"];
        return;
    }
#endif
    self.readyFile = [NSTemporaryDirectory() stringByAppendingPathComponent:
        [NSString stringWithFormat:@"softloaf-%@.json", NSUUID.UUID.UUIDString]];
    NSString *output = [checkout stringByAppendingPathComponent:@"artifacts/application"];
    [[NSFileManager defaultManager] createDirectoryAtPath:output withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *log = [output stringByAppendingPathComponent:@"desktop.log"];
    [[NSFileManager defaultManager] createFileAtPath:log contents:[NSData data] attributes:nil];
    NSFileHandle *logHandle = [NSFileHandle fileHandleForWritingAtPath:log];
    self.service = [NSTask new];
    self.service.executableURL = [NSURL fileURLWithPath:python];
    self.service.currentDirectoryURL = [NSURL fileURLWithPath:checkout];
#if SOFTLOAF_PACKAGED_SERVICE
    self.service.arguments = @[@"--ready-file",self.readyFile,@"--parent-pid",[NSString stringWithFormat:@"%d",getpid()]];
#else
    self.service.arguments = @[@"-m", @"spectral_app", @"--core",
        [resource stringByAppendingPathComponent:@"libsoftloaf_core.dylib"],
        @"--ready-file", self.readyFile, @"--parent-pid", [NSString stringWithFormat:@"%d", getpid()]];
#endif
    self.service.standardOutput = logHandle; self.service.standardError = logHandle;
    // Child runs the configured environment without inheriting Python injection settings.
    self.service.environment = [self serviceEnvironment];
    NSError *error = nil;
    if (![self.service launchAndReturnError:&error]) {
        [self failure:@"无法启动本地计算服务。请检查 Python 环境和开发版构建。"];
        return;
    }
    self.started = [NSDate date];
    self.readiness = [NSTimer scheduledTimerWithTimeInterval:.2 target:self
        selector:@selector(checkReady:) userInfo:nil repeats:YES];
}
- (void)checkReady:(NSTimer *)timer {
    if (!self.service.running || -self.started.timeIntervalSinceNow > 45) {
        [timer invalidate];
        [self failure:@"光谱服务未就绪。请先运行启动检查；本地材料和 OpenDRT 数据均需齐全。诊断记录位于 artifacts/application/desktop.log。"];
        return;
    }
    NSData *data = [NSData dataWithContentsOfFile:self.readyFile];
    if (!data) return;
    NSDictionary *ready = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    NSURL *url = [NSURL URLWithString:ready[@"url"] ?: @""];
    if (![ready[@"pid"] isEqual:@(self.service.processIdentifier)] ||
        ![url.host isEqualToString:@"127.0.0.1"] || ![url.scheme isEqualToString:@"http"] || !url.port) return;
    [timer invalidate]; self.baseURL = url;
    [self.loading removeFromSuperview];self.loading = nil;
    [self createWebView];
    [self recordLayout:@"installed" details:@{}];
    [self.web loadRequest:[NSURLRequest requestWithURL:url]];
}
- (void)createWebView {
    WKWebViewConfiguration *webConfiguration = [[WKWebViewConfiguration alloc] init];
    [webConfiguration.userContentController addScriptMessageHandler:self name:@"cacheFolder"];
    [webConfiguration.userContentController addScriptMessageHandler:self name:@"uiLanguage"];
    webConfiguration.websiteDataStore = WKWebsiteDataStore.nonPersistentDataStore;
    self.web = [[WKWebView alloc] initWithFrame:self.window.contentLayoutRect configuration:webConfiguration];
    self.web.navigationDelegate = self; self.web.UIDelegate = self;
    SLInstallContentView(self.window, self.web);
}
- (void)recordLayout:(NSString *)phase details:(NSDictionary *)details {
    NSDictionary *record = @{ @"phase":phase,@"web_frame":NSStringFromRect(self.web.frame),
        @"root_frame":NSStringFromRect(self.window.contentView.frame),@"visible_rect":NSStringFromRect(self.window.contentLayoutRect),@"window_visible":@(self.window.visible),@"occlusion":@(self.window.occlusionState),@"view_hidden":@(self.web.hidden),@"view_layer":@(self.web.wantsLayer),
        @"details":details };
    NSData *bytes = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingPrettyPrinted error:nil];
    NSString *path = [self.service.currentDirectoryURL.path stringByAppendingPathComponent:@"artifacts/application/native-layout.json"];
    [bytes writeToFile:path atomically:YES];
}
- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation {
    (void)navigation;
    // On the tested macOS 27 WebKit, first navigation can leave a blank drawing
    // area until a geometry update despite a correct DOM viewport. Refresh only
    // the view once; the outer window and the user's window size stay unchanged.
    if (!self.refreshedDrawingArea && NSWidth(webView.frame)>1) {
        self.refreshedDrawingArea = YES;
        NSRect frame = webView.frame;frame.size.width -= 1;webView.frame = frame;
        dispatch_async(dispatch_get_main_queue(), ^{
            NSRect final = self.window.contentLayoutRect;
            if (self.window.styleMask & NSWindowStyleMaskFullSizeContentView) final = self.web.superview.bounds;
            self.web.frame = final;
            self.web.needsDisplay = YES;[self.window displayIfNeeded];
        });
    }
    [webView evaluateJavaScript:@"({width:innerWidth,height:innerHeight,ready:document.readyState,children:document.body.children.length,display:getComputedStyle(document.body).display,opacity:getComputedStyle(document.body).opacity,appRect:JSON.stringify(document.querySelector('.app').getBoundingClientRect())})"
        completionHandler:^(id result,NSError *error) {
            [self recordLayout:@"loaded" details:error ? @{@"error":error.localizedDescription} : ([result isKindOfClass:NSDictionary.class] ? result : @{})];
        }];
}
- (void)webViewWebContentProcessDidTerminate:(WKWebView *)webView {
    (void)webView;[self recordLayout:@"web-process-terminated" details:@{}];
}
- (void)showAbout:(id)sender {
    (void)sender;
    [NSApp orderFrontStandardAboutPanelWithOptions:@{NSAboutPanelOptionApplicationName: self.window.title}];
}
- (void)openSettings:(id)sender {
    (void)sender;
    [self.web evaluateJavaScript:@"window.softloafOpenSettings?.()" completionHandler:nil];
}
- (void)userContentController:(WKUserContentController *)controller didReceiveScriptMessage:(WKScriptMessage *)message {
    (void)controller;
    if (!message.frameInfo.mainFrame || ![self localURL:message.frameInfo.request.URL]) return;
    if ([message.name isEqualToString:@"uiLanguage"]) {
        if (![message.body isKindOfClass:NSString.class] ||
            ![@[@"en",@"zh-CN"] containsObject:message.body]) return;
        BOOL english = [message.body isEqualToString:@"en"];
        self.window.title = english ? @"SoftLoaf Spectral" : @"面包光谱";
        NSMenu *applicationMenu = [NSApp.mainMenu itemAtIndex:0].submenu;
        [applicationMenu itemAtIndex:0].title = english ? @"About SoftLoaf Spectral" : @"关于面包光谱";
        [applicationMenu itemAtIndex:2].title = english ? @"Settings…" : @"设置…";
        [applicationMenu itemAtIndex:4].title = english ? @"Quit SoftLoaf Spectral" : @"退出面包光谱";
        NSMenuItem *editItem = [NSApp.mainMenu itemAtIndex:1];
        editItem.title = english ? @"Edit" : @"编辑";
        NSArray *titles = english ? @[@"Cut",@"Copy",@"Paste",@"Select All"] : @[@"剪切",@"复制",@"粘贴",@"全选"];
        for (NSUInteger i=0;i<titles.count;++i) [editItem.submenu itemAtIndex:i].title=titles[i];
        return;
    }
    if (![message.name isEqualToString:@"cacheFolder"]) return;
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.canChooseFiles = NO; panel.canChooseDirectories = YES; panel.allowsMultipleSelection = NO;
    panel.message = @"选择 T7 上的缓存文件夹";
    panel.directoryURL = [NSURL fileURLWithPath:@"/Volumes/T7 Touch"];
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
        if (response != NSModalResponseOK) return;
        NSData *data = [NSJSONSerialization dataWithJSONObject:@[panel.URL.path] options:0 error:nil];
        NSString *encoded = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
        NSString *script = [NSString stringWithFormat:@"window.softloafCacheLocationSelection?.((%@)[0])",encoded];
        [self.web evaluateJavaScript:script completionHandler:nil];
    }];
}
- (BOOL)localURL:(NSURL *)url {
    return [url.scheme isEqualToString:@"http"] && [url.host isEqualToString:@"127.0.0.1"] &&
        [url.port isEqual:self.baseURL.port];
}
- (void)webView:(WKWebView *)webView decidePolicyForNavigationAction:(WKNavigationAction *)action
    decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    (void)webView;
    NSURL *url = action.request.URL;
    BOOL blob = [url.absoluteString hasPrefix:[@"blob:" stringByAppendingString:self.baseURL.absoluteString]];
    if ([self localURL:url] || blob) {
        decisionHandler(action.shouldPerformDownload ? WKNavigationActionPolicyDownload : WKNavigationActionPolicyAllow);
    } else {
        decisionHandler(WKNavigationActionPolicyCancel);
        if (action.navigationType == WKNavigationTypeLinkActivated && [url.scheme isEqualToString:@"https"])
            [NSWorkspace.sharedWorkspace openURL:url];
    }
}
- (void)webView:(WKWebView *)webView decidePolicyForNavigationResponse:(WKNavigationResponse *)response
    decisionHandler:(void (^)(WKNavigationResponsePolicy))decisionHandler {
    (void)webView;
    NSDictionary *headers = [response.response isKindOfClass:NSHTTPURLResponse.class] ?
        [(NSHTTPURLResponse *)response.response allHeaderFields] : @{};
    NSString *disposition = headers[@"Content-Disposition"];
    decisionHandler([disposition.lowercaseString hasPrefix:@"attachment"] || !response.canShowMIMEType ?
        WKNavigationResponsePolicyDownload : WKNavigationResponsePolicyAllow);
}
- (void)webView:(WKWebView *)webView navigationAction:(WKNavigationAction *)action didBecomeDownload:(WKDownload *)download {
    (void)webView; (void)action; [self.downloads addObject:download]; download.delegate = self;
}
- (void)webView:(WKWebView *)webView navigationResponse:(WKNavigationResponse *)response didBecomeDownload:(WKDownload *)download {
    (void)webView; (void)response; [self.downloads addObject:download]; download.delegate = self;
}
- (void)download:(WKDownload *)download decideDestinationUsingResponse:(NSURLResponse *)response
    suggestedFilename:(NSString *)filename completionHandler:(void (^)(NSURL *))completionHandler {
    (void)download; (void)response;
    NSSavePanel *panel = [NSSavePanel savePanel];
    panel.nameFieldStringValue = filename.lastPathComponent;
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse result) {
        completionHandler(result == NSModalResponseOK ? panel.URL : nil);
    }];
}
- (void)downloadDidFinish:(WKDownload *)download { [self.downloads removeObject:download]; }
- (void)download:(WKDownload *)download didFailWithError:(NSError *)error resumeData:(NSData *)resumeData {
    (void)resumeData; [self.downloads removeObject:download];
    if (error.code == NSURLErrorCancelled) return;
    NSAlert *alert = [NSAlert new]; alert.messageText = @"文件未保存";
    alert.informativeText = @"请重新下载并选择一个可写入的位置。";
    [alert beginSheetModalForWindow:self.window completionHandler:nil];
}
- (void)webView:(WKWebView *)webView runOpenPanelWithParameters:(WKOpenPanelParameters *)parameters
    initiatedByFrame:(WKFrameInfo *)frame completionHandler:(void (^)(NSArray<NSURL *> *))completionHandler {
    (void)webView; (void)frame;
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.canChooseDirectories = NO; panel.canChooseFiles = YES;
    panel.allowsMultipleSelection = parameters.allowsMultipleSelection;
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse result) {
        completionHandler(result == NSModalResponseOK ? panel.URLs : nil);
    }];
}

- (BOOL)windowShouldClose:(NSWindow *)sender {
    (void)sender;
    [NSApp terminate:nil];
    return NO;
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    (void)sender;
    if (!self.web || self.quitting || !self.service.running) return NSTerminateNow;
    [self.web callAsyncJavaScript:@"return await window.softloafFlushSession();" arguments:@{}
        inFrame:nil inContentWorld:WKContentWorld.pageWorld completionHandler:^(id result, NSError *error) {
            if (!error && [result isKindOfClass:NSDictionary.class] && [result[@"ok"] boolValue]) {
                [NSApp replyToApplicationShouldTerminate:YES];
                return;
            }
            NSAlert *alert = [NSAlert new];
            alert.messageText = @"还有未保存的编辑";
            alert.informativeText = [result isKindOfClass:NSDictionary.class] ?
                (result[@"reason"] ?: @"请先保存当前配方。") : @"请等待工作区就绪，或先保存当前配方。";
            [alert addButtonWithTitle:@"保留编辑"]; [alert addButtonWithTitle:@"退出"];
            [alert beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
                [NSApp replyToApplicationShouldTerminate:response == NSAlertSecondButtonReturn];
            }];
        }];
    return NSTerminateLater;
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender { (void)sender; return YES; }
- (void)applicationWillTerminate:(NSNotification *)notification {
    (void)notification; self.quitting = YES; [self.readiness invalidate];
    if (self.service.running) [self.service terminate];
    if (self.readyFile) [[NSFileManager defaultManager] removeItemAtPath:self.readyFile error:nil];
}
@end

int main(int argc, const char *argv[]) {
    (void)argc; (void)argv;
    @autoreleasepool {
        NSApplication *app = NSApplication.sharedApplication;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        SpectralApp *delegate = [SpectralApp new]; app.delegate = delegate;
        [app run];
    }
    return 0;
}
