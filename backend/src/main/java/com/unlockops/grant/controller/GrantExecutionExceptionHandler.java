package com.unlockops.grant.controller;

import com.unlockops.grant.dto.GrantExecutionResponses.*;
import com.unlockops.grant.dto.GrantExecutionResponses.Error;
import com.unlockops.grant.service.GrantExecutionException;
import com.unlockops.common.error.ApiError;
import org.springframework.core.annotation.Order;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.dao.RecoverableDataAccessException;
import org.springframework.jdbc.CannotGetJdbcConnectionException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice(assignableTypes = InternalGrantController.class)
@Order(-1)
public class GrantExecutionExceptionHandler {
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> invalidPath() {
        return ResponseEntity.badRequest().body(new ApiError("입력 형식과 필수 항목을 확인해 주세요."));
    }

    @ExceptionHandler(GrantExecutionException.class)
    public ResponseEntity<Failure> execution(GrantExecutionException e) {
        return ResponseEntity.status(e.status()).body(new Failure(false,
            new Error(e.code(), e.getMessage(), e.retryable(), e.reason())));
    }

    @ExceptionHandler({TransientDataAccessException.class, RecoverableDataAccessException.class, CannotGetJdbcConnectionException.class})
    public ResponseEntity<Failure> transientDatabaseFailure() {
        return ResponseEntity.status(503).body(new Failure(false,
            new Error("UPSTREAM_UNAVAILABLE", "일시적인 DB 오류로 실행하지 못했습니다.", true, null)));
    }
}
