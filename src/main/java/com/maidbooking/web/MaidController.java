package com.maidbooking.web;

import com.maidbooking.domain.Gender;
import com.maidbooking.domain.Maid;
import com.maidbooking.domain.ServiceType;
import com.maidbooking.domain.TimeSlot;
import com.maidbooking.exception.InvalidRequestException;
import com.maidbooking.search.MaidSearchCriteria;
import com.maidbooking.search.MaidSearchService;
import com.maidbooking.service.MaidService;
import com.maidbooking.service.OnboardMaidCommand;
import com.maidbooking.web.MaidDtos.AddMaidRequest;
import com.maidbooking.web.MaidDtos.MaidResponse;
import com.maidbooking.web.MaidDtos.WindowDto;
import jakarta.validation.Valid;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Set;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/maids")
public class MaidController {
    private static final int DEFAULT_SEARCH_DURATION_MINUTES = 60;

    private final MaidService maidService;
    private final MaidSearchService searchService;

    public MaidController(MaidService maidService, MaidSearchService searchService) {
        this.maidService = maidService;
        this.searchService = searchService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public MaidResponse add(@Valid @RequestBody AddMaidRequest r) {
        Maid maid = maidService.onboard(new OnboardMaidCommand(r.name(), r.locality(), r.gender(), r.rating(),
                r.hourlyRates(), r.skills(), r.availability().stream().map(WindowDto::toDomain).toList()));
        return MaidResponse.from(maid);
    }

    @GetMapping("/{id}")
    public MaidResponse get(@PathVariable String id) {
        return MaidResponse.from(maidService.get(id));
    }

    @GetMapping("/search")
    public List<MaidResponse> search(
            @RequestParam(required = false) String locality,
            @RequestParam(required = false) ServiceType serviceType,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.TIME) LocalTime startTime,
            @RequestParam(required = false) Integer durationMinutes,
            @RequestParam(required = false) Double minRating,
            @RequestParam(required = false) BigDecimal maxHourlyRate,
            @RequestParam(required = false) Gender gender,
            @RequestParam(required = false) Set<String> skills) {
        MaidSearchCriteria criteria = new MaidSearchCriteria(locality, serviceType,
                requestedSlot(date, startTime, durationMinutes), minRating, maxHourlyRate, gender, skills);
        return searchService.search(criteria).stream().map(MaidResponse::from).toList();
    }

    private TimeSlot requestedSlot(LocalDate date, LocalTime startTime, Integer durationMinutes) {
        if (date == null && startTime == null) {
            if (durationMinutes != null) throw new InvalidRequestException("durationMinutes needs date and startTime");
            return null;
        }
        if (date == null || startTime == null) {
            throw new InvalidRequestException("date and startTime must be provided together");
        }
        return TimeSlot.of(date.atTime(startTime), durationMinutes == null ? DEFAULT_SEARCH_DURATION_MINUTES : durationMinutes);
    }
}
