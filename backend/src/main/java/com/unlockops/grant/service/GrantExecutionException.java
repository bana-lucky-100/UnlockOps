package com.unlockops.grant.service;

import org.springframework.http.HttpStatus;

/** 실행 실패는 예외로 전파해 변경·차감·영수증을 함께 롤백한다. */
public class GrantExecutionException extends RuntimeException {
    private final HttpStatus status;
    private final String code;
    private final boolean retryable;
    private final String reason;

    public GrantExecutionException(HttpStatus status, String code, String message, boolean retryable, String reason) {
        super(message);
        this.status = status; this.code = code; this.retryable = retryable; this.reason = reason;
    }
    public HttpStatus status() { return status; }
    public String code() { return code; }
    public boolean retryable() { return retryable; }
    public String reason() { return reason; }

    public static GrantExecutionException conflict(String code) {
        return new GrantExecutionException(HttpStatus.CONFLICT, code, "승인 또는 실행 조건이 변경되어 처리할 수 없습니다.", false, null);
    }
    public static GrantExecutionException precondition(String reason) {
        return new GrantExecutionException(HttpStatus.CONFLICT, "PRECONDITION_CHANGED", "현재 부여 조건을 충족하지 않습니다.", false, reason);
    }
}
