package com.unlockops.phase2.common;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.common.json.Jsons;
import com.unlockops.contracts.v2.Phase2Codec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Small JDBC/JSON boundary; workflow transactions live in the domain services. */
@Repository
public class Phase2Store {
    public final JdbcTemplate jdbc;
    public final Jsons json;
    public final Phase2Codec codec = new Phase2Codec();
    public Phase2Store(JdbcTemplate jdbc, Jsons json) { this.jdbc=jdbc; this.json=json; }
    public List<JsonNode> rows(String sql, Object... args) {
        return jdbc.query(sql, (rs,n)->json.tree(rs.getString(1)),args);
    }
    public JsonNode one(String sql, Object... args) {
        var rows=rows(sql,args);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"대상을 찾을 수 없습니다.");
        if(rows.size()!=1) throw new IllegalStateException("Expected one row");
        return rows.getFirst();
    }
    public boolean exists(String sql,Object... args) { return Boolean.TRUE.equals(jdbc.queryForObject(sql,Boolean.class,args)); }
    public JsonNode problem(UUID id,boolean lock) {
        return one("SELECT to_jsonb(p) FROM problems p WHERE id=? AND contract_version=2"+(lock?" FOR UPDATE":""),id);
    }
    public JsonNode run(UUID id,boolean lock) {
        return one("SELECT to_jsonb(r) FROM reclaim_runs r WHERE id=?"+(lock?" FOR UPDATE":""),id);
    }
    public void mutex(String key) { jdbc.query("SELECT pg_advisory_xact_lock(hashtextextended(?,0))",rs->{},key); }
    public <T> T decode(JsonNode node,Class<T> type) { return codec.read(node.toString(),type); }
    public <T> T checked(T value,Class<T> type) { return codec.read(json.write(value),type); }
    public static UUID uuid(JsonNode n,String field) { return n.path(field).isNull()||n.path(field).isMissingNode()?null:UUID.fromString(n.path(field).asText()); }
    public static String str(JsonNode n,String field) { return n.path(field).isNull()||n.path(field).isMissingNode()?null:n.path(field).asText(); }
    public static void conflict(boolean ok,String message) { if(!ok) throw new ResponseStatusException(HttpStatus.CONFLICT,message); }
    public static void forbid(boolean ok) { if(!ok) throw new ResponseStatusException(HttpStatus.FORBIDDEN,"허용된 조직·업무 범위가 아닙니다."); }
    public static String key(String value) {
        if(value==null||value.isBlank()||value.length()>128) throw new IllegalArgumentException("Idempotency-Key required (1..128)");
        return value;
    }
    public static String hash(String text) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8))); }
        catch(Exception e) { throw new IllegalStateException(e); }
    }
}
