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
    private static final org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(ApiExceptionHandler.class);
    public record CodedError(String message, String code, boolean retryable) {}

    @ExceptionHandler(org.springframework.web.servlet.resource.NoResourceFoundException.class)
    public ResponseEntity<ApiError> notFound() {
        return ResponseEntity.status(404).body(new ApiError("요청한 API를 찾을 수 없습니다."));
    }

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

    @ExceptionHandler({IllegalArgumentException.class, MethodArgumentNotValidException.class, HttpMessageNotReadableException.class,
        org.springframework.web.bind.MissingRequestHeaderException.class,
        org.springframework.web.method.annotation.MethodArgumentTypeMismatchException.class})
    public ResponseEntity<ApiError> invalid(Exception e) {
        return ResponseEntity.badRequest().body(new ApiError("입력 형식과 필수 항목을 확인해 주세요."));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> unexpected(Exception e) {
        log.error("Unhandled exception", e);
        return ResponseEntity.internalServerError().body(new ApiError("서버 처리 중 오류가 발생했습니다."));
    }
}
