package com.maidbooking.search;

import com.maidbooking.domain.Maid;

@FunctionalInterface
public interface MaidFilter {
    boolean test(Maid maid);
}
