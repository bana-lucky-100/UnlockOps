package com.unlockops.common.error;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** 문서 오류를 일시적인 통신·DB 장애와 구분해 MCP까지 전달한다. */
public class PolicySourceUnavailableException extends ResponseStatusException {
    public PolicySourceUnavailableException() {
        super(HttpStatus.SERVICE_UNAVAILABLE, "회사 권한표의 적용 기준을 확인할 수 없습니다.");
    }
}
