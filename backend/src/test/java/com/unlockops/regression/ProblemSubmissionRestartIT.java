package com.unlockops.regression;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.unlockops.Application;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.junit.jupiter.api.Assertions.*;

/** Two full Spring web-server lifecycles share only the disposable durable services, not sessions or beans. */
@Testcontainers
class ProblemSubmissionRestartIT {
    @Container static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");
    @Container static final RabbitMQContainer BROKER = new RabbitMQContainer("rabbitmq:4-management-alpine");

    @Test void replaySurvivesServerRestartAndChangedDemoPolicy() throws Exception {
        String key = UUID.randomUUID().toString();
        JsonNode first = null;
        for (int run = 0; run < 2; run++) {
            try (var context = new SpringApplicationBuilder(Application.class).run(
                "--server.port=0", "--spring.datasource.url=" + POSTGRES.getJdbcUrl(),
                "--spring.datasource.username=" + POSTGRES.getUsername(), "--spring.datasource.password=" + POSTGRES.getPassword(),
                "--spring.rabbitmq.host=" + BROKER.getHost(), "--spring.rabbitmq.port=" + BROKER.getAmqpPort(),
                "--spring.rabbitmq.username=" + BROKER.getAdminUsername(), "--spring.rabbitmq.password=" + BROKER.getAdminPassword(),
                "--spring.rabbitmq.listener.simple.auto-startup=false", "--app.demo-enabled=" + (run == 0),
                "--app.demo-password=restart-password", "--spring.main.banner-mode=off",
                "--logging.level.org.springframework=WARN", "--logging.level.com.unlockops=WARN")) {
                int port = ((WebServerApplicationContext) context).getWebServer().getPort();
                String base = "http://localhost:" + port;
                ObjectMapper json = context.getBean(ObjectMapper.class);
                try (HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10))
                        .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL)).build()) {
                    JsonNode csrf = csrf(client, base, json);
                    var login = post(client, base + "/api/auth/login", csrf, null,
                        "{\"loginId\":\"kim_dev\",\"password\":\"restart-password\"}");
                    assertEquals(200, login.statusCode());
                    var response = post(client, base + "/api/problems", csrf(client, base, json), key,
                        "{\"platform\":\"JIRA\",\"contents\":\"PAY\",\"simulateJiraFailure\":true}");
                    assertEquals(202, response.statusCode(), response.body());
                    JsonNode body = json.readTree(response.body());
                    if (run == 0) first = body;
                    else assertEquals(first, body);
                }
                JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
                assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM problems", Integer.class));
                assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM outbox WHERE routing_key='analysis'", Integer.class));
            }
        }
    }

    private JsonNode csrf(HttpClient client, String base, ObjectMapper json) throws Exception {
        var response = client.send(HttpRequest.newBuilder(URI.create(base + "/api/auth/csrf")).GET().build(),
            HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode());
        return json.readTree(response.body());
    }

    private HttpResponse<String> post(HttpClient client, String url, JsonNode csrf, String key, String body) throws Exception {
        var request = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(15))
            .header("Content-Type", "application/json")
            .header(csrf.path("headerName").asText(), csrf.path("token").asText());
        if (key != null) request.header("Idempotency-Key", key);
        return client.send(request.POST(HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
    }
}
