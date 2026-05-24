import { StackTraceTopoReader, RuntimeTraceBuilder, JCrossVault, ErrorContext } from './src/verantyx/memory/runtime-ir';

const rawTrace = `Exception in thread "Thread-15" java.lang.NullPointerException: userDB is null
  at com.auth.UserAuthService.validateToken(UserAuthService.java:127)
  at com.auth.AuthController.authenticate(AuthController.java:45)
  at com.pipeline.AsyncExecutor.run(AsyncExecutor.java:201)
  at java.lang.Thread.run(Thread.java:834)`;

const vault = new JCrossVault();
const reader = new StackTraceTopoReader(vault);
const builder = new RuntimeTraceBuilder();

const frames = reader.parseStacktrace(rawTrace);

const errCtx: ErrorContext = {
    captureTimeMs: Date.now(),
    errorType: "NullPointerException",
    message: "userDB is null",
    computeSignature: () => "HASH_NPE_AUTH"
};

const topology = builder.buildTopologyTrace(frames, errCtx);
console.log(topology.toJCross6AxisFormat());
