package com.unlockops.phase2.common;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.Phase2Types.PolicyEvidence;
import java.util.*;
import static com.unlockops.phase2.common.Phase2Store.*;

/** Exact immutable excerpts; matches the Policy MCP heading boundaries. */
public final class PolicyArticles {
    private PolicyArticles() {}
    public static List<PolicyEvidence> reclaim(JsonNode policy) {
        var all=new ArrayList<PolicyEvidence>();
        for(String section:str(policy,"content").split("(?m)(?=^## )")) {
            if(!section.startsWith("## "))continue;
            String article=section.lines().findFirst().orElse("").substring(3).strip();
            if((article.startsWith("POL-06") && article.contains("제5조")) || article.startsWith("GH-OFF-03") || (article.startsWith("BASELINE") && article.contains("회수")))
                all.add(new PolicyEvidence(str(policy,"doc_id"),article,str(policy,"revision"),str(policy,"source_hash"),section.strip()));
        }
        if(all.isEmpty())all.add(new PolicyEvidence(str(policy,"doc_id"),str(policy,"article"),str(policy,"revision"),str(policy,"source_hash"),str(policy,"content")));
        return all;
    }
}
