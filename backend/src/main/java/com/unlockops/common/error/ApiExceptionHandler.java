package com.unlockops.common.error;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
public class ApiExceptionHandler {
    public record CodedError(String message, String code, boolean retryable) {}

    @ExceptionHandler(PolicySourceUnavailableException.class)
    public ResponseEntity<CodedError> policySource(PolicySourceUnavailableException e) {
        return ResponseEntity.status(503).body(new CodedError(e.getReason(), "POLICY_SOURCE_UNAVAILABLE", false));
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ApiError> status(ResponseStatusException e) {
        return ResponseEntity.status(e.getStatusCode()).body(new ApiError(e.getReason() == null ? "요청을 처리할 수 없습니다." : e.getReason()));
    }

    @ExceptionHandler(BadCredentialsException.class)
    public ResponseEntity<ApiError> credentials() {
        return ResponseEntity.status(401).body(new ApiError("로그인 정보를 확인해 주세요."));
    }

    @ExceptionHandler({IllegalArgumentException.class, MethodArgumentNotValidException.class, HttpMessageNotReadableException.class})
    public ResponseEntity<ApiError> invalid(Exception e) {
        return ResponseEntity.badRequest().body(new ApiError("입력 형식과 필수 항목을 확인해 주세요."));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> unexpected(Exception e) {
        return ResponseEntity.internalServerError().body(new ApiError("서버 처리 중 오류가 발생했습니다."));
    }
}
