package com.unlockops.access.service;

import com.unlockops.access.dto.AccessContextResponses.Profile;
import com.unlockops.auth.model.*;
import com.unlockops.grant.model.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AccessCeilingPolicy {
    private static final String SOURCE = "company-a-access-matrix.md";
    private static final Pattern SECTION = Pattern.compile("(?ms)^## 3\\.[^\\n]*\\n(.*?)(?=^## \\d+\\.|\\z)");
    private static final Pattern GRADE = Pattern.compile("사원|대리|과장|차장|부장");
    private static final Set<String> ROLES = Set.of("Read", "Write", "Viewer", "Developer", "Can view", "Can edit", "Member", "Seat");
    private final Path path;

    public AccessCeilingPolicy(@Value("${app.access-matrix-path:}") String configuredPath) {
        // 루트와 backend 디렉터리 실행을 지원한다. 배포에서는 경로를 명시한다.
        path = configuredPath.isBlank() ? (Files.exists(Path.of("data", SOURCE)) ?
            Path.of("data", SOURCE) : Path.of("..", "data", SOURCE)) : Path.of(configuredPath);
    }

    /** RAG와 같은 원문을 한 번 읽어 상한과 그 원문의 해시를 함께 반환한다. */
    public Ceiling ceiling(Profile profile, Resource resource) {
        try {
            byte[] bytes = Files.readAllBytes(path);
            String text = new String(bytes, StandardCharsets.UTF_8);
            String role = parse(text, profile, resource);
            String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
            return new Ceiling(role, Map.of(SOURCE, hash));
        } catch (IOException | NoSuchAlgorithmException e) {
            throw unavailable();
        }
    }

    /** 실행은 상한뿐 아니라 승인자 기준과 분석 근거의 최신 원문 버전을 함께 확인한다. */
    public ExecutionRules executionRules(Profile profile, Resource resource) {
        try {
            byte[] matrix = Files.readAllBytes(path);
            byte[] corpus = Files.readAllBytes(path.resolveSibling("policy_corpus.md"));
            String text = new String(matrix, StandardCharsets.UTF_8);
            var section = Pattern.compile("(?ms)^## 7\\.[^\\n]*\\n(.*?)(?=^## \\d+\\.|\\z)").matcher(text);
            if (!section.find()) throw unavailable();
            String rules = section.group(1);
            var minimum = Pattern.compile("승인자는 앱 역할이 ([A-Z_]+)이고 직급이 (사원|대리|과장|차장|부장) 이상").matcher(rules);
            if (!minimum.find()) throw unavailable();
            UserRole approverRole;
            try { approverRole = UserRole.valueOf(minimum.group(1)); }
            catch (IllegalArgumentException e) { throw unavailable(); }
            boolean tf = resource.accessScope() == AccessScope.TF;
            var rows = rules.lines().map(String::strip).filter(line -> line.startsWith("|"))
                .map(line -> line.replace("*", "").split("\\|"))
                .filter(cells -> cells.length == 3 && (tf ? cells[1].strip().startsWith("TF 전용") :
                    cells[1].strip().startsWith("일반·"))).toList();
            if (rows.size() != 1 || !rows.getFirst()[2].contains(tf ? "리더" : "부서장")) throw unavailable();
            return new ExecutionRules(parse(text, profile, resource), Map.of(SOURCE, hash(matrix),
                "policy_corpus.md", hash(corpus)), approverRole, JobGrade.from(minimum.group(2)));
        } catch (IOException | NoSuchAlgorithmException e) { throw unavailable(); }
    }

    private String hash(byte[] bytes) throws NoSuchAlgorithmException {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    private String parse(String text, Profile profile, Resource resource) {
        var section = SECTION.matcher(text);
        if (!section.find()) throw unavailable();
        List<List<String>> rows = section.group(1).lines().map(String::strip).filter(line -> line.startsWith("|"))
            .map(line -> Arrays.stream(line.substring(1, line.endsWith("|") ? line.length() - 1 : line.length()).split("\\|", -1))
                .map(cell -> cell.replace("*", "").replace("`", "").strip()).toList())
            .filter(row -> !row.stream().allMatch(cell -> cell.matches("[-:\\s]+"))).toList();
        if (rows.isEmpty()) throw unavailable();
        String family = profile.jobFamily() == JobFamily.DEV ? "개발" : "비개발";
        List<Integer> columns = new ArrayList<>();
        for (int i = 2; i < rows.getFirst().size(); i++) {
            String header = rows.getFirst().get(i);
            if (header.matches(Pattern.quote(family) + "(?:\\s+(?:사원|대리|과장|차장|부장)(?:\\s+이상)?|\\(전 직급\\))")
                    && gradeMatches(header, profile.jobGrade())) columns.add(i);
        }
        String scope = switch (resource.accessScope()) {
            case GENERAL -> "일반"; case TF -> "TF 전용"; case SEAT -> "유료 좌석";
            case DEPARTMENT -> "부서 내부"; case CONFIDENTIAL -> "기밀";
        };
        var matches = rows.stream().skip(1).filter(row -> row.size() == rows.getFirst().size()
            && row.get(0).equalsIgnoreCase(resource.platform().name()) && row.get(1).startsWith(scope)).toList();
        if (columns.size() != 1 || matches.size() != 1) throw unavailable();
        String cell = matches.getFirst().get(columns.getFirst());
        if (cell.equals("신청 불가")) return "";
        var parts = Arrays.stream(cell.split(",")).map(String::strip)
            .filter(part -> gradeMatches(part, profile.jobGrade())).toList();
        if (parts.size() != 1) throw unavailable();
        String role = parts.getFirst().replaceFirst("^(?:사원|대리|과장|차장|부장)(?:\\s+이상)?\\s+", "");
        role = switch (role) { case "좌석" -> "Seat"; case "참여" -> "Member"; default -> role; };
        if (!ROLES.contains(role)) throw unavailable();
        return role;
    }

    private boolean gradeMatches(String text, JobGrade grade) {
        var matcher = GRADE.matcher(text);
        if (!matcher.find()) return true;
        JobGrade threshold = JobGrade.from(matcher.group());
        return text.contains("이상") ? grade.atLeast(threshold) : grade == threshold;
    }

    private ResponseStatusException unavailable() {
        return new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "회사 권한표의 적용 기준을 확인할 수 없습니다.");
    }

    public record Ceiling(String role, Map<String, String> sourceHashes) {}
    public record ExecutionRules(String role, Map<String, String> sourceHashes, UserRole approverRole, JobGrade minimumGrade) {}
}
