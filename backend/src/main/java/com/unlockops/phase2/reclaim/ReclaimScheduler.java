package com.unlockops.phase2.reclaim;

import com.unlockops.phase2.common.Phase2Store;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
public class ReclaimScheduler {
    private static final Logger log=LoggerFactory.getLogger(ReclaimScheduler.class);
    private final Phase2Store db;
    private final ReclaimWorkflowService service;
    private final boolean enabled;
    public ReclaimScheduler(Phase2Store db,ReclaimWorkflowService service,@Value("${app.phase2-reclaim-schedule-enabled:false}") boolean enabled) {
        this.db=db;this.service=service;this.enabled=enabled;
    }
    @Scheduled(cron="${app.phase2-reclaim-cron:0 0 9 * * *}",zone="Asia/Seoul")
    public void daily() {
        if(!enabled)return;
        for(var s:db.rows("SELECT to_jsonb(s) FROM reclaim_scopes s WHERE enabled ORDER BY id")) {
            try {service.scheduled(Phase2Store.uuid(s,"id"));}
            catch(Exception e) {log.warn("Reclaim scheduling deferred: scope={}, exception={}",s.path("id").asText(),e.getClass().getSimpleName());}
        }
    }
}
