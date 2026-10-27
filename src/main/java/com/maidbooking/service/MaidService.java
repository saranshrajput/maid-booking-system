package com.maidbooking.service;

import com.maidbooking.domain.Maid;
import com.maidbooking.exception.NotFoundException;
import com.maidbooking.repository.MaidRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class MaidService {
    private final MaidRepository maidRepository;

    public MaidService(MaidRepository maidRepository) {
        this.maidRepository = maidRepository;
    }

    public Maid onboard(OnboardMaidCommand c) {
        Maid maid = new Maid(UUID.randomUUID().toString(), c.name(), c.locality(), c.gender(), c.rating(),
                c.hourlyRates(), c.skills(), c.availability());
        return maidRepository.save(maid);
    }

    public Maid get(String id) {
        return maidRepository.findById(id).orElseThrow(() -> new NotFoundException("Maid not found: " + id));
    }
}
