package com.unlockops.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class AuthDtos {
    private AuthDtos() {}
    public record Login(@NotBlank @Size(max = 255) String loginId, @NotBlank @Size(max = 200) String password) {}
    public record DemoLogin(@NotBlank @Size(max = 255) String loginId) {}
    public record CsrfResponse(String token, String headerName) {}
}
