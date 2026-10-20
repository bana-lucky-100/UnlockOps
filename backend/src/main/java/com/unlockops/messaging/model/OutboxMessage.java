package com.unlockops.messaging.model;

import java.util.UUID;

public record OutboxMessage(UUID eventId, String routingKey, String payload) {}
