package com.unlockops.messaging.service;

/** A result that requires a producer/contract correction rather than another consumer attempt. */
public class InvalidAgentMessageException extends RuntimeException {
    public enum Reason {
        INVALID_ENVELOPE, INVALID_RESULT, UNKNOWN_RESULT_KIND, ILLEGAL_RESULT_STATE,
        UNVERIFIED_COMPLETION, MISSING_RECEIPT
    }

    public InvalidAgentMessageException(Reason reason) { super(reason.name()); }
    public InvalidAgentMessageException(Reason reason, Throwable cause) { super(reason.name(), cause); }
}
