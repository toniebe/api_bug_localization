// NOTE: The following script syntax is valid for database version 5.0 and above.

:param {
  // Define the file path root and the individual file names required for loading.
  // https://neo4j.com/docs/operations-manual/current/configuration/file-locations/
  file_path_root: 'file:///', // Change this to the folder your script can access the files at.
  file_0: 'bugs_with_labels.csv',
  file_1: 'topics_cleaned.csv',
  file_2: 'developer_topic_profile.csv',
  file_3: 'bug_relations.csv'
};

// CONSTRAINT creation
// -------------------
//
// Create node uniqueness constraints, ensuring no duplicates for the given node label and ID property exist in the database. This also ensures no duplicates are introduced in future.
//
CREATE CONSTRAINT `id_bug_uniq` IF NOT EXISTS
FOR (n: `bug`)
REQUIRE (n.`id`) IS UNIQUE;
CREATE CONSTRAINT `topic_id_topic_uniq` IF NOT EXISTS
FOR (n: `topic`)
REQUIRE (n.`topic_id`) IS UNIQUE;
CREATE CONSTRAINT `assigned_to_developer_uniq` IF NOT EXISTS
FOR (n: `developer`)
REQUIRE (n.`assigned_to`) IS UNIQUE;

:param {
  idsToSkip: []
};

// NODE load
// ---------
//
// Load nodes in batches, one node label at a time. Nodes will be created using a MERGE statement to ensure a node with the same label and ID property remains unique. Pre-existing nodes found by a MERGE statement will have their other properties set to the latest values encountered in a load file.
//
// NOTE: Any nodes with IDs in the 'idsToSkip' list parameter will not be loaded.
LOAD CSV WITH HEADERS FROM ($file_path_root + $file_0) AS row
WITH row
WHERE NOT row.`id` IN $idsToSkip AND NOT toInteger(trim(row.`id`)) IS NULL
CALL (row) {
  MERGE (n: `bug` { `id`: toInteger(trim(row.`id`)) })
  SET n.`id` = toInteger(trim(row.`id`))
  SET n.`clean_text` = row.`clean_text`
  SET n.`summary` = row.`summary`
  SET n.`creator` = row.`creator`
  SET n.`assigned_to` = row.`assigned_to`
  SET n.`status` = row.`status`
  SET n.`resolution` = row.`resolution`
  // Your script contains the datetime datatype. Our app attempts to convert dates to ISO 8601 date format before passing them to the Cypher function.
  // This conversion cannot be done in a Cypher script load. Please ensure that your CSV file columns are in ISO 8601 date format to ensure equivalent loads.
  SET n.`creation_time` = datetime(row.`creation_time`)
  // Your script contains the datetime datatype. Our app attempts to convert dates to ISO 8601 date format before passing them to the Cypher function.
  // This conversion cannot be done in a Cypher script load. Please ensure that your CSV file columns are in ISO 8601 date format to ensure equivalent loads.
  SET n.`last_change_time` = datetime(row.`last_change_time`)
  SET n.`dominant_topic` = toInteger(trim(row.`dominant_topic`))
  SET n.`topic_score` = toFloat(trim(row.`topic_score`))
  SET n.`topic_id` = toInteger(trim(row.`topic_id`))
  SET n.`topic_label` = row.`topic_label`
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM ($file_path_root + $file_1) AS row
WITH row
WHERE NOT row.`topic_id` IN $idsToSkip AND NOT toInteger(trim(row.`topic_id`)) IS NULL
CALL (row) {
  MERGE (n: `topic` { `topic_id`: toInteger(trim(row.`topic_id`)) })
  SET n.`topic_id` = toInteger(trim(row.`topic_id`))
  SET n.`terms` = row.`terms`
  SET n.`clean_terms` = row.`clean_terms`
  SET n.`topic_label` = row.`topic_label`
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM ($file_path_root + $file_2) AS row
WITH row
WHERE NOT row.`assigned_to` IN $idsToSkip AND NOT row.`assigned_to` IS NULL
CALL (row) {
  MERGE (n: `developer` { `assigned_to`: row.`assigned_to` })
  SET n.`assigned_to` = row.`assigned_to`
  SET n.`t0` = toFloat(trim(row.`t0`))
  SET n.`t1` = toFloat(trim(row.`t1`))
  SET n.`t2` = toFloat(trim(row.`t2`))
  SET n.`t3` = toFloat(trim(row.`t3`))
  SET n.`t4` = toFloat(trim(row.`t4`))
  SET n.`t5` = toFloat(trim(row.`t5`))
  SET n.`t6` = toFloat(trim(row.`t6`))
  SET n.`t7` = toFloat(trim(row.`t7`))
  SET n.`dominant_topic` = toInteger(trim(row.`dominant_topic`))
} IN TRANSACTIONS OF 10000 ROWS;


// RELATIONSHIP load
// -----------------
//
// Load relationships in batches, one relationship type at a time. Relationships are created using a MERGE statement, meaning only one relationship of a given type will ever be created between a pair of nodes.
LOAD CSV WITH HEADERS FROM ($file_path_root + $file_0) AS row
WITH row 
CALL (row) {
  MATCH (source: `bug` { `id`: toInteger(trim(row.`id`)) })
  MATCH (target: `topic` { `topic_id`: toInteger(trim(row.`dominant_topic`)) })
  MERGE (source)-[r: `IN_TOPIC`]->(target)
  SET r.`topic_score` = toFloat(trim(row.`topic_score`))
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM ($file_path_root + $file_0) AS row
WITH row 
CALL (row) {
  MATCH (source: `bug` { `id`: toInteger(trim(row.`id`)) })
  MATCH (target: `developer` { `assigned_to`: row.`assigned_to` })
  MERGE (source)-[r: `ASSIGNED_TO`]->(target)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM ($file_path_root + $file_3) AS row
WITH row 
CALL (row) {
  MATCH (source: `bug` { `id`: toInteger(trim(row.`bug_a`)) })
  MATCH (target: `bug` { `id`: toInteger(trim(row.`bug_b`)) })
  MERGE (source)-[r: `SIMILAR_TO`]->(target)
} IN TRANSACTIONS OF 10000 ROWS;
