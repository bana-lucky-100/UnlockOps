-- HTTP submission identity is separate from the approved grant's idempotency_key.
-- Historical/legacy clients without a key keep independent request creation.
ALTER TABLE problems ADD COLUMN client_request_key VARCHAR(128);

CREATE UNIQUE INDEX problems_requester_client_request_key
ON problems(requester_id, client_request_key)
WHERE client_request_key IS NOT NULL;
