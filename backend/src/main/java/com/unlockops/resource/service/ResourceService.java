package com.unlockops.resource.service;

import com.unlockops.resource.dto.ResourceRequests.Resolve;
import com.unlockops.resource.dto.ResourceResponses.*;
import com.unlockops.resource.model.ResourceCandidate;
import com.unlockops.resource.repository.ResourceRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.springframework.stereotype.Service;

@Service
public class ResourceService {
    private final ResourceRepository resources;
    public ResourceService(ResourceRepository resources) { this.resources = resources; }

    /** 명시된 이름만 찾는다. 완전 일치를 우선하고 복수 후보를 임의로 선택하지 않는다. */
    public Resolved resolve(Resolve request) {
        String hint = normalize(request.hint().strip());
        if (hint.isEmpty()) return new Resolved(List.of(), true);
        List<ResourceCandidate> exact = new ArrayList<>(), contained = new ArrayList<>();
        for (ResourceCandidate resource : resources.findByPlatform(request.platform())) {
            List<String> names = Stream.concat(Stream.of(resource.externalId(), resource.name()),
                resource.aliases().stream()).map(ResourceService::normalize).toList();
            if (names.contains(hint)) exact.add(resource);
            else if (names.stream().anyMatch(name -> name.codePointCount(0, name.length()) >= 3 && mentioned(hint, name)))
                contained.add(resource);
        }
        var matches = (exact.isEmpty() ? contained : exact).stream().map(Match::from).toList();
        return new Resolved(matches, matches.size() != 1);
    }

    private static String normalize(String value) { return value.toLowerCase(Locale.ROOT); }

    private static boolean mentioned(String hint, String name) {
        if (name.matches("[a-z0-9_-]+"))
            return Pattern.compile("(?<![a-z0-9_-])" + Pattern.quote(name) + "(?![a-z0-9_-])")
                .matcher(hint).find();
        return hint.contains(name);
    }
}
