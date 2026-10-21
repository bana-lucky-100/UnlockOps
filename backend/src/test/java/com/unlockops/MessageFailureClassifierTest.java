package com.unlockops;

import com.unlockops.messaging.service.InvalidAgentMessageException;
import com.unlockops.messaging.service.MessageFailureClassifier;
import java.net.ConnectException;
import java.sql.SQLException;
import java.sql.SQLTransientConnectionException;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.support.ListenerExecutionFailedException;
import org.springframework.dao.CannotAcquireLockException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.jdbc.CannotGetJdbcConnectionException;
import org.springframework.transaction.CannotCreateTransactionException;

import static com.unlockops.messaging.service.MessageFailureClassifier.Failure.*;
import static com.unlockops.messaging.service.InvalidAgentMessageException.Reason.*;
import static org.junit.jupiter.api.Assertions.*;

class MessageFailureClassifierTest {
    final MessageFailureClassifier classifier = new MessageFailureClassifier();

    @Test void wrappedDatabaseContentionAndTimeoutAreRetryable() {
        assertEquals(TRANSIENT_DATABASE, classifier.classify(new ListenerExecutionFailedException("listener",
            new CannotAcquireLockException("contention"))));
        assertEquals(TRANSIENT_DATABASE, classifier.classify(new QueryTimeoutException("timeout")));
    }

    @Test void transactionCreationFailureExaminesDatabaseConnectionCause() {
        assertEquals(TRANSIENT_DATABASE, classifier.classify(new CannotCreateTransactionException("transaction",
            new CannotGetJdbcConnectionException("connection", new SQLException("offline", "08006")))));
        assertEquals(TRANSIENT_DATABASE, classifier.classify(new CannotGetJdbcConnectionException("connection",
            new SQLException("connection", new ConnectException("refused")))));
    }

    @Test void authenticationFailureInsidePoolTimeoutMustNotRetry() {
        SQLException authentication = new SQLException("sensitive authentication details", "28P01");
        var timeout = new SQLTransientConnectionException("pool timeout", authentication);
        assertEquals(PERMANENT_DATABASE, classifier.classify(new CannotGetJdbcConnectionException("connection", timeout)));
    }

    @Test void databaseConstraintAndSyntaxErrorsAreNotRetryable() {
        assertEquals(PERMANENT_DATABASE, classifier.classify(new DataIntegrityViolationException("constraint")));
        assertEquals(PERMANENT_DATABASE, classifier.classify(new SQLException("syntax", "42601")));
    }

    @Test void explicitMessageRejectionTakesPrecedenceOverNestedTransientCause() {
        assertEquals(INVALID_MESSAGE, classifier.classify(new InvalidAgentMessageException(INVALID_RESULT,
            new QueryTimeoutException("nested"))));
    }

    @Test void unclassifiedAndNonDatabaseNetworkErrorsDoNotRetry() {
        assertEquals(UNKNOWN, classifier.classify(new IllegalStateException("defect")));
        assertEquals(UNKNOWN, classifier.classify(new ConnectException("unrelated network call")));
    }

    @Test void cyclicCauseChainDoesNotHangTheConsumer() {
        var first = new RuntimeException();
        var second = new RuntimeException(first);
        first.initCause(second);
        assertEquals(UNKNOWN, classifier.classify(first));
    }
}
