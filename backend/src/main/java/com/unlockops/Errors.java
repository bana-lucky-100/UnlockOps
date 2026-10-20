package com.unlockops;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
class Errors {
    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<?> status(ResponseStatusException e) {
        return ResponseEntity.status(e.getStatusCode()).body(Map.of("message",e.getReason()==null?"요청을 처리할 수 없습니다.":e.getReason()));
    }
    @ExceptionHandler(BadCredentialsException.class)
    ResponseEntity<?> credentials() { return ResponseEntity.status(401).body(Map.of("message","로그인 정보를 확인해 주세요.")); }
    @ExceptionHandler({IllegalArgumentException.class,MethodArgumentNotValidException.class})
    ResponseEntity<?> invalid(Exception e) { return ResponseEntity.badRequest().body(Map.of("message","입력 형식과 필수 항목을 확인해 주세요.")); }
    @ExceptionHandler(Exception.class)
    ResponseEntity<?> unexpected(Exception e) { return ResponseEntity.internalServerError().body(Map.of("message","서버 처리 중 오류가 발생했습니다.")); }
}
