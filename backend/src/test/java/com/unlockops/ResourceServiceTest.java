package com.unlockops;

import com.unlockops.grant.model.*;
import com.unlockops.resource.dto.ResourceRequests.Resolve;
import com.unlockops.resource.model.ResourceCandidate;
import com.unlockops.resource.repository.ResourceRepository;
import com.unlockops.resource.service.ResourceService;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ResourceServiceTest {
    private final ResourceRepository repository = mock(ResourceRepository.class);
    private final ResourceService service = new ResourceService(repository);

    private ResourceCandidate resource(String key, String name, String... aliases) {
        return new ResourceCandidate(UUID.randomUUID(), Platform.GITHUB, key, name, List.of(aliases),
            AccessScope.GENERAL, null, null, SecurityGrade.INTERNAL, null);
    }

    @Test void explicitExternalIdMatchesWithoutGuessingOrChangingCase() {
        var candidate = resource("payment-core", "결제 저장소");
        when(repository.findByPlatform(Platform.GITHUB)).thenReturn(List.of(candidate));
        var result = service.resolve(new Resolve(Platform.GITHUB, "PAYMENT-CORE에 push가 안 돼요"));
        assertFalse(result.ambiguous());
        assertEquals(candidate.id(), result.matches().getFirst().id());
        assertEquals("payment-core", result.matches().getFirst().externalId());
        verify(repository).findByPlatform(Platform.GITHUB);
    }

    @Test void exactAliasWinsOverOtherContainedNamesAndAllowsShortAlias() {
        var exact = resource("payment-core", "결제 저장소", "PAY access", "pc");
        when(repository.findByPlatform(Platform.GITHUB)).thenReturn(List.of(
            resource("access", "권한 저장소"), exact));
        assertEquals(exact.id(), service.resolve(new Resolve(Platform.GITHUB, " PAY ACCESS "))
            .matches().getFirst().id());
        assertEquals(exact.id(), service.resolve(new Resolve(Platform.GITHUB, "pc"))
            .matches().getFirst().id());
    }

    @Test void namesAndAliasesAreMatchedAndMultipleCandidatesStayAmbiguous() {
        when(repository.findByPlatform(Platform.GITHUB)).thenReturn(List.of(
            resource("payment-core", "결제 저장소", "결제코어"), resource("payment-api", "결제 API")));
        var result = service.resolve(new Resolve(Platform.GITHUB, "결제코어와 payment-api가 안 열려요"));
        assertTrue(result.ambiguous());
        assertEquals(2, result.matches().size());
        assertFalse(service.resolve(new Resolve(Platform.GITHUB, "결제 저장소가 안 보여요")).ambiguous());
    }

    @Test void asciiBoundariesDoNotMatchInsideAnotherResourceOrShortAlias() {
        when(repository.findByPlatform(Platform.GITHUB)).thenReturn(List.of(
            resource("payment-core", "결제 저장소", "pc")));
        for (String hint : List.of("my-payment-core", "payment-core-extra", "xpayment-core", "pc가 안 열려요", "없음")) {
            var result = service.resolve(new Resolve(Platform.GITHUB, hint));
            assertTrue(result.ambiguous(), hint);
            assertTrue(result.matches().isEmpty(), hint);
        }
    }

    @Test void emptyHintDoesNotReadTheCatalog() {
        var result = service.resolve(new Resolve(Platform.GITHUB, "   "));
        assertTrue(result.ambiguous());
        assertTrue(result.matches().isEmpty());
        verifyNoInteractions(repository);
    }
}
