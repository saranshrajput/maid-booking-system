package com.maidbooking.search;

import com.maidbooking.domain.Maid;
import com.maidbooking.repository.MaidRepository;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class MaidSearchService {
    private final MaidRepository maidRepository;
    private final List<MaidFilterProvider> providers;

    public MaidSearchService(MaidRepository maidRepository, List<MaidFilterProvider> providers) {
        this.maidRepository = maidRepository;
        this.providers = providers;
    }

    public List<Maid> search(MaidSearchCriteria criteria) {
        List<MaidFilter> filters = providers.stream().map(p -> p.create(criteria)).flatMap(Optional::stream).toList();
        return maidRepository.findAll().stream()
                .filter(m -> filters.stream().allMatch(f -> f.test(m)))
                .sorted(Comparator.comparingDouble(Maid::getRating).reversed().thenComparing(Maid::getName))
                .toList();
    }
}
