package com.unlockops.messaging.model;

public enum QueueRoute {
    ANALYSIS("analysis"), EXECUTION("execution"), RESULTS("results"), DEAD("dead");

    public static final String EXCHANGE = "unlockops";
    public static final String RESULTS_QUEUE = "unlockops.results";
    private final String key;

    QueueRoute(String key) { this.key = key; }
    public String key() { return key; }
    public String queue() { return EXCHANGE + "." + key; }
}
