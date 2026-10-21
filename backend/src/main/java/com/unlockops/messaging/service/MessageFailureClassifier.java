package com.unlockops.messaging.service;

import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.sql.SQLException;
import java.sql.SQLRecoverableException;
import java.sql.SQLTransientException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;
import org.springframework.amqp.support.converter.MessageConversionException;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.RecoverableDataAccessException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.CannotCreateTransactionException;

/** Retry only known database failures; uncertainty must not create an automatic retry loop. */
public class MessageFailureClassifier {
    public enum Failure {
        TRANSIENT_DATABASE, PERMANENT_DATABASE, INVALID_MESSAGE, UNKNOWN;
        public boolean retryable() { return this == TRANSIENT_DATABASE; }
    }

    public Failure classify(Throwable failure) {
        List<Throwable> causes = causes(failure);
        if (causes.stream().anyMatch(cause -> cause instanceof InvalidAgentMessageException
            || cause instanceof MessageConversionException
            || cause instanceof org.springframework.messaging.converter.MessageConversionException))
            return Failure.INVALID_MESSAGE;
        // A pool can wrap an authentication failure in a transient connection timeout. Inspect denials first.
        if (causes.stream().anyMatch(cause -> cause instanceof DataIntegrityViolationException
            || cause instanceof SQLException sql && permanentSqlState(sql.getSQLState())))
            return Failure.PERMANENT_DATABASE;
        if (causes.stream().anyMatch(cause -> cause instanceof TransientDataAccessException
            || cause instanceof RecoverableDataAccessException || cause instanceof SQLTransientException
            || cause instanceof SQLRecoverableException
            || cause instanceof SQLException sql && transientSqlState(sql.getSQLState())))
            return Failure.TRANSIENT_DATABASE;
        boolean databaseBoundary = causes.stream().anyMatch(cause -> cause instanceof DataAccessException
            || cause instanceof CannotCreateTransactionException);
        if (databaseBoundary && causes.stream().anyMatch(cause -> cause instanceof ConnectException
            || cause instanceof SocketTimeoutException)) return Failure.TRANSIENT_DATABASE;
        return Failure.UNKNOWN;
    }

    private boolean permanentSqlState(String state) {
        return state != null && state.length() >= 2
            && Set.of("22", "23", "28", "3D", "3F", "42").contains(state.substring(0, 2));
    }

    private boolean transientSqlState(String state) {
        return state != null && Set.of("08000", "08001", "08003", "08006", "08007",
            "40001", "40P01", "55P03", "57014").contains(state);
    }

    private List<Throwable> causes(Throwable failure) {
        Set<Throwable> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        List<Throwable> causes = new ArrayList<>();
        for (Throwable cause = failure; cause != null && visited.add(cause); cause = cause.getCause()) causes.add(cause);
        return causes;
    }
}
