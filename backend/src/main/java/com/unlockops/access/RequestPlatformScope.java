package com.unlockops.access;

import com.unlockops.contracts.v2.WorkflowTypes.Platform;
import java.util.*;
import java.util.regex.Pattern;

/** First named platform owns one request; remaining platforms require separate requests. */
final class RequestPlatformScope {
    private RequestPlatformScope() {}
    static String mask(String text) {
        return text.replaceAll("(?<!\\d)(?:\\+82[- .]?)?0?1[016789][- .]?\\d{3,4}[- .]?\\d{4}(?!\\d)","[전화번호 삭제]")
            .replaceAll("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}","[이메일 삭제]")
            .replaceAll("(?:주소|거주지)\\s*[:：]\\s*[^\\n;]+","[주소 삭제]")
            .replaceAll("(?:[가-힣]+(?:특별시|광역시|도)\\s+)?[가-힣]+[시군구]\\s+(?:[가-힣]+[시군구]\\s+)?[가-힣0-9]+(?:로|길|동)\\s*\\d+(?:-\\d+)?(?:\\s+\\d+동)?(?:\\s+\\d+호)?","[주소 삭제]");
    }
    private static final Map<Platform,String> ALIASES=Map.of(
        Platform.GITHUB,"github|copilot|깃허브|코파일럿",Platform.JIRA,"jira|지라",
        Platform.SLACK,"slack|슬랙",Platform.NOTION,"notion|노션",
        Platform.SNOWFLAKE,"snowflake|스노우플레이크",Platform.DATABRICKS,"databricks|데이터브릭스",
        Platform.SALESFORCE,"salesforce|세일즈포스",Platform.DATADOG,"datadog|데이터독",
        Platform.TABLEAU_CLOUD,"tableau(?: cloud)?|태블로",Platform.FIGMA,"figma|피그마");
    static List<Platform> mentioned(String text) {
        var positions=new TreeMap<Integer,Platform>();
        ALIASES.forEach((platform,aliases)->{
            var matcher=Pattern.compile("(?<![a-z])(?:"+aliases+")(?![a-z])",Pattern.CASE_INSENSITIVE).matcher(text);
            if(matcher.find())positions.put(matcher.start(),platform);
        });
        return List.copyOf(positions.values());
    }
    static String notice(String contents) {
        var names=mentioned(contents);
        return names.size()<2?"":" 이번 접수는 "+names.getFirst()+"만 처리합니다. "+String.join(", ",names.subList(1,names.size()).stream().map(Enum::name).toList())+" 권한은 별도로 접수해 주세요.";
    }
}
