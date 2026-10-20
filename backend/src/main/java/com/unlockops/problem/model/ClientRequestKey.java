package com.unlockops.problem.model;

import java.util.regex.Pattern;

/** An opaque, case-sensitive HTTP submission key, scoped to the authenticated requester. */
public record ClientRequestKey(String value) {
    private static final Pattern VALID = Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    public ClientRequestKey {
        if (value == null || !VALID.matcher(value).matches())
            throw new IllegalArgumentException("Invalid Idempotency-Key");
    }
}
