package com.unlockops.regression;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import org.testcontainers.containers.RabbitMQContainer;

/** Opt-in screenshots of the disposable broker and measured DB results; never connects to a development stack. */
final class RetryEvidence {
    private RetryEvidence() {}

    static void capture(ObjectNode evidence, RabbitMQContainer broker, ObjectMapper json) throws Exception {
        if (!Boolean.getBoolean("retry.capture")) return;
        Path output = Path.of("target", "retry-evidence").toAbsolutePath();
        Files.createDirectories(output);
        ObjectNode input = evidence.deepCopy();
        input.put("managementUrl", "http://" + broker.getHost() + ":" + broker.getHttpPort());
        input.put("username", broker.getAdminUsername()).put("password", broker.getAdminPassword());
        input.put("output", output.toString());
        Path script = Path.of("..", "tests", "capture-message-retry.mjs").toAbsolutePath();
        Process capture = new ProcessBuilder("node", script.toString()).redirectErrorStream(true)
            .redirectOutput(output.resolve(evidence.path("scenario").asText() + ".capture.log").toFile()).start();
        // Disposable broker credentials go through stdin and are not retained in the evidence JSON.
        try (var stdin = capture.getOutputStream()) { stdin.write(json.writeValueAsBytes(input)); }
        if (!capture.waitFor(60, TimeUnit.SECONDS)) {
            capture.destroyForcibly();
            throw new IllegalStateException("Screenshot timed out; inspect target/retry-evidence capture logs");
        }
        if (capture.exitValue() != 0)
            throw new IllegalStateException("Screenshot failed; inspect target/retry-evidence capture logs");
    }
}
