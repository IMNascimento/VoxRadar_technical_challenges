package com.kwai.sig3;

import com.github.unidbg.AndroidEmulator;
import com.github.unidbg.Module;
import com.github.unidbg.arm.Arm64Svc;
import com.github.unidbg.linux.android.AndroidEmulatorBuilder;
import com.github.unidbg.linux.android.AndroidResolver;
import com.github.unidbg.linux.android.dvm.AbstractJni;
import com.github.unidbg.linux.android.dvm.BaseVM;
import com.github.unidbg.linux.android.dvm.DalvikModule;
import com.github.unidbg.linux.android.dvm.DvmClass;
import com.github.unidbg.linux.android.dvm.DvmObject;
import com.github.unidbg.linux.android.dvm.StringObject;
import com.github.unidbg.linux.android.dvm.VM;
import com.github.unidbg.linux.android.dvm.VaList;
import com.github.unidbg.linux.android.dvm.array.ArrayObject;
import com.github.unidbg.linux.android.dvm.jni.ProxyClassFactory;
import com.github.unidbg.linux.android.dvm.wrapper.DvmBoolean;
import com.github.unidbg.linux.android.dvm.wrapper.DvmInteger;
import com.github.unidbg.memory.Memory;
import com.github.unidbg.virtualmodule.android.AndroidModule;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class KwaiSign extends AbstractJni {

    // Caminhos relativos ao diretorio onde o processo java e iniciado
    // (server/, ver run.bat) -- o servidor agora e autocontido dentro de
    // kwai-collector/server, sem depender de apk/tools/unidbg/.
    private static final String SO_PATH = "libkwsgmain.so";
    private static final String APK_PATH = "rootfs/data/app/~~ZNQl4e4b1NCm_hu8qBUnTg==/kwai.lite.video-Jt2OvP6kyHNAB7v2n61WQQ==/base.apk";
    private static final String REAL_APPID = "8e58d8f8-0d73-44d8-807d-d03ddd523804";
    private static final String REAL_CODE_PATH = "/data/app/~~ZNQl4e4b1NCm_hu8qBUnTg==/kwai.lite.video-Jt2OvP6kyHNAB7v2n61WQQ==/base.apk";

    private final AndroidEmulator emulator;
    private final VM vm;
    private final DvmClass cJNICLibrary;
    private DvmObject<?> context;

    public KwaiSign() {
        emulator = AndroidEmulatorBuilder.for64Bit()
                .setProcessName("kwai.lite.video")
                .setRootDir(new File("rootfs"))
                .build();
        Memory memory = emulator.getMemory();
        memory.setLibraryResolver(new AndroidResolver(23));
        vm = emulator.createDalvikVM(new File(APK_PATH));
        vm.setJni(this);
        vm.setVerbose(false);
        new AndroidModule(emulator, vm).register(memory);
        patchMissingAssetDirSymbols(memory.findModule("libandroid.so"));

        DalvikModule dm = vm.loadLibrary(new File(SO_PATH), false);
        cJNICLibrary = vm.resolveClass("com/kuaishou/android/security/internal/dispatch/JNICLibrary");
        dm.callJNI_OnLoad(emulator);

        DvmClass cApplication = vm.resolveClass("android/app/Application");
        context = cApplication.newObject(null);

        System.out.println("[KwaiSign] vm.getPackageName() = " + vm.getPackageName());
        System.out.println("[KwaiSign] vm.getSignatures() = " + java.util.Arrays.toString(vm.getSignatures()));
    }

    private void patchMissingAssetDirSymbols(Module libandroid) {
        libandroid.registerSymbol("AAssetManager_openDir", emulator.getSvcMemory().registerSvc(new Arm64Svc() {
            @Override
            public long handle(com.github.unidbg.Emulator<?> emulator) {
                return 0L;
            }
        }).peer);
        libandroid.registerSymbol("AAssetDir_getNextFileName", emulator.getSvcMemory().registerSvc(new Arm64Svc() {
            @Override
            public long handle(com.github.unidbg.Emulator<?> emulator) {
                return 0L;
            }
        }).peer);
        libandroid.registerSymbol("AAssetDir_close", emulator.getSvcMemory().registerSvc(new Arm64Svc() {
            @Override
            public long handle(com.github.unidbg.Emulator<?> emulator) {
                return 0L;
            }
        }).peer);
    }

    @Override
    public DvmObject<?> callObjectMethodV(BaseVM vm, DvmObject<?> dvmObject, String signature, VaList vaList) {
        switch (signature) {
            case "android/app/Application->getPackageCodePath()Ljava/lang/String;":
            case "android/content/Context->getPackageCodePath()Ljava/lang/String;":
            case "android/content/ContextWrapper->getPackageCodePath()Ljava/lang/String;":
                return new StringObject(vm, REAL_CODE_PATH);
            case "android/app/Application->getPackageName()Ljava/lang/String;":
            case "android/content/Context->getPackageName()Ljava/lang/String;":
            case "android/content/ContextWrapper->getPackageName()Ljava/lang/String;":
                return new StringObject(vm, vm.getPackageName());
            default:
                System.out.println("[KwaiSign] unhandled callObjectMethodV: " + signature);
                return super.callObjectMethodV(vm, dvmObject, signature, vaList);
        }
    }

    @Override
    public boolean callBooleanMethodV(BaseVM vm, DvmObject<?> dvmObject, String signature, VaList vaList) {
        if ("java/lang/Boolean->booleanValue()Z".equals(signature)) {
            return (Boolean) dvmObject.getValue();
        }
        return super.callBooleanMethodV(vm, dvmObject, signature, vaList);
    }

    @Override
    public int callIntMethodV(BaseVM vm, DvmObject<?> dvmObject, String signature, VaList vaList) {
        if ("java/lang/Integer->intValue()I".equals(signature)) {
            return (Integer) dvmObject.getValue();
        }
        return super.callIntMethodV(vm, dvmObject, signature, vaList);
    }

    @Override
    public void callStaticVoidMethodV(BaseVM vm, DvmClass dvmClass, String signature, VaList vaList) {
        if ("com/kuaishou/android/security/internal/common/ExceptionProxy->nativeReport(ILjava/lang/String;)V".equals(signature)) {
            System.out.println("[KwaiSign] ignoring nativeReport call");
            return;
        }
        super.callStaticVoidMethodV(vm, dvmClass, signature, vaList);
    }

    public Object callDoCommand(int cmd, DvmObject<?>... args) {
        ArrayObject argsArray = new ArrayObject(args);
        System.out.println("[KwaiSign] calling doCommandNative cmd=0x" + Integer.toHexString(cmd) + " (" + cmd + ")");
        DvmObject<?> result = cJNICLibrary.callStaticJniMethodObject(emulator,
                "doCommandNative(I[Ljava/lang/Object;)Ljava/lang/Object;", cmd, argsArray);
        System.out.println("[KwaiSign] result = " + (result == null ? "null" : result.getValue()));
        return result == null ? null : result.getValue();
    }

    public void init() {
        callDoCommand(0x28ac,
                null,
                new StringObject(vm, REAL_APPID),
                null,
                null,
                context,
                null,
                null);
    }

    private final Object signLock = new Object();

    public String signSync(String stringToSign) {
        synchronized (signLock) {
            return sign(stringToSign);
        }
    }

    public String sign(String stringToSign) {
        ArrayObject arr = ArrayObject.newStringArray(vm, stringToSign);
        Object result = callDoCommand(0x28b2,
                arr,
                new StringObject(vm, REAL_APPID),
                DvmInteger.valueOf(vm, -1),
                DvmBoolean.valueOf(vm, false),
                context,
                null,
                DvmBoolean.valueOf(vm, false),
                new StringObject(vm, ""));
        return result == null ? null : result.toString();
    }

    public void destroy() throws Exception {
        emulator.close();
    }

    private static void runServer(KwaiSign k, int port) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/health", new HttpHandler() {
            @Override
            public void handle(HttpExchange exchange) throws IOException {
                byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                OutputStream os = exchange.getResponseBody();
                os.write(body);
                os.close();
            }
        });
        server.createContext("/sign", new HttpHandler() {
            @Override
            public void handle(HttpExchange exchange) throws IOException {
                if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                    exchange.sendResponseHeaders(405, -1);
                    exchange.close();
                    return;
                }
                String stringToSign = readAll(exchange.getRequestBody());
                String result;
                int status;
                try {
                    result = k.signSync(stringToSign);
                    status = 200;
                    if (result == null) {
                        result = "";
                        status = 204;
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                    result = "error: " + e;
                    status = 500;
                }
                byte[] body = result.getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(status == 204 ? 204 : status, status == 204 ? -1 : body.length);
                if (status != 204) {
                    OutputStream os = exchange.getResponseBody();
                    os.write(body);
                    os.close();
                } else {
                    exchange.close();
                }
            }
        });
        server.setExecutor(null);
        server.start();
        System.out.println("[KwaiSign] servidor pronto em http://127.0.0.1:" + port + " (POST /sign, GET /health)");
    }

    private static String readAll(InputStream in) throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) != -1) {
            bos.write(buf, 0, n);
        }
        return new String(bos.toByteArray(), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        KwaiSign k = new KwaiSign();
        k.init();

        if (args.length > 0 && "--serve".equals(args[0])) {
            int port = args.length > 1 ? Integer.parseInt(args[1]) : 8765;
            runServer(k, port);
            return;
        }

        if (args.length > 0) {
            String stringToSign = new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(args[0])), StandardCharsets.UTF_8);
            String result = k.sign(stringToSign);
            System.out.println("SIG3_RESULT:" + result);
        } else {
            System.out.println("=== signing call cmd=0x28b2 (10418) ===");
            System.out.println(k.sign("POST&/rest/o/comment/list/v2&teste=1"));
            System.out.println("=== signing call AGAIN same input (determinism check) ===");
            System.out.println(k.sign("POST&/rest/o/comment/list/v2&teste=1"));
        }

        k.destroy();
    }
}
