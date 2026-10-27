package com.maidbooking.search;

import java.util.Optional;

// Add a new search filter by adding one @Component implementing this; nothing else changes.
public interface MaidFilterProvider {
    Optional<MaidFilter> create(MaidSearchCriteria criteria);
}
