package com.unlockops.approval.dto;

public record ApprovalSummaryResponse(String department, long memberCount, long weekRequests,
                                      long approved, long rejected, long failed) {}
