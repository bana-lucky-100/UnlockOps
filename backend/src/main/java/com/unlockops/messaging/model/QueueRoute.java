package com.unlockops.messaging.model;

public enum QueueRoute {
    ANALYSIS("v2.analysis"), EXECUTION("v2.execution"), RESULTS("results"), DEAD("dead");

    public static final String EXCHANGE = "unlockops";
    public static final String RESULTS_QUEUE = "unlockops.results";
    private final String key;

    QueueRoute(String key) { this.key = key; }
    public String key() { return key; }
    public String queue() { return EXCHANGE + "." + key; }
}
