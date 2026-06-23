// Query 1: pretty Browser graph for one user (good for screenshot)
MATCH (u:User {user_ref: 'user_0001'})-[pref:PREFERS]->(c:Category)
OPTIONAL MATCH (u)-[:PERFORMED]->(b:Behavior)-[:IN_CATEGORY]->(c)
OPTIONAL MATCH (b)-[:ON_PRODUCT]->(p:Product)
WITH u, pref, c, b, p
ORDER BY b.event_ts DESC
RETURN u, pref, c, b, p
LIMIT 40;

// Query 2: top preferred categories for one user
MATCH (u:User {user_ref: 'user_0001'})-[pref:PREFERS]->(c:Category)
RETURN
  u.user_ref AS user_ref,
  c.slug AS category_slug,
  c.name AS category_name,
  pref.rank AS preference_rank,
  pref.score AS affinity_score,
  pref.share AS affinity_share,
  pref.event_count AS event_count
ORDER BY pref.rank ASC, pref.score DESC;

// Query 3: product/context lookup for chat by user and category
MATCH (u:User {user_ref: 'user_0001'})-[pref:PREFERS]->(c:Category {slug: 'audio'})
OPTIONAL MATCH (u)-[:PERFORMED]->(b:Behavior)-[:IN_CATEGORY]->(c)
OPTIONAL MATCH (b)-[:ON_PRODUCT]->(p:Product)
WITH c, pref, b, p
ORDER BY b.event_ts DESC
RETURN
  c.slug AS category_slug,
  c.name AS category_name,
  pref.score AS affinity_score,
  collect(DISTINCT b.behavior_type)[0..6] AS recent_behaviors,
  collect(DISTINCT p {
    .product_id,
    .name,
    .brand,
    .price,
    .stock
  })[0..8] AS related_products;

// Query 4: category-product overview for submission screenshot
MATCH (c:Category)<-[:BELONGS_TO]-(p:Product)
RETURN c, p
LIMIT 50;

// Query 5: users who strongly prefer a category
MATCH (u:User)-[pref:PREFERS]->(c:Category {slug: 'smartphones'})
WHERE pref.share >= 0.35
RETURN
  u.user_ref AS user_ref,
  pref.score AS affinity_score,
  pref.share AS affinity_share,
  u.event_count AS total_events
ORDER BY pref.score DESC, pref.share DESC
LIMIT 20;
