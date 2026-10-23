package com.unlockops.resource.repository;

import com.unlockops.common.json.Jsons;
import com.unlockops.grant.model.*;
import com.unlockops.resource.model.ResourceCandidate;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ResourceRepository {
    private final JdbcTemplate jdbc;
    private final Jsons json;

    public ResourceRepository(JdbcTemplate jdbc, Jsons json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    public List<ResourceCandidate> findByPlatform(Platform platform) {
        return jdbc.query("""
            SELECT id,platform,external_id,name,aliases,access_scope,owner_department_id,
                   tf_id,security_grade,designated_department_id
            FROM resources WHERE company_id='00000000-0000-0000-0000-000000000000' AND platform=? ORDER BY external_id
            """, (rs, n) -> new ResourceCandidate(rs.getObject("id", UUID.class),
                Platform.valueOf(rs.getString("platform")), rs.getString("external_id"), rs.getString("name"),
                Arrays.asList(json.read(json.tree(rs.getString("aliases")), String[].class)),
                AccessScope.valueOf(rs.getString("access_scope")), rs.getObject("owner_department_id", UUID.class),
                rs.getObject("tf_id", UUID.class), rs.getString("security_grade") == null ? null :
                    SecurityGrade.valueOf(rs.getString("security_grade")),
                rs.getObject("designated_department_id", UUID.class)), platform.name());
    }
}
