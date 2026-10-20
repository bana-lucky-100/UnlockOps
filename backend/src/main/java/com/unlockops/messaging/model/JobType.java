package com.unlockops.messaging.model;

public enum JobType {
    ANALYZE(QueueRoute.ANALYSIS), EXECUTE(QueueRoute.EXECUTION);

    private final QueueRoute route;
    JobType(QueueRoute route) { this.route = route; }
    public String routingKey() { return route.key(); }
}
