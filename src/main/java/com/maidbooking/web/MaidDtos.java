package com.maidbooking.web;

import com.maidbooking.domain.AvailabilityWindow;
import com.maidbooking.domain.Gender;
import com.maidbooking.domain.Maid;
import com.maidbooking.domain.ServiceType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.DayOfWeek;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class MaidDtos {
    private MaidDtos() {
    }

    public record WindowDto(@NotNull DayOfWeek day, @NotNull LocalTime start, @NotNull LocalTime end) {
        AvailabilityWindow toDomain() {
            return new AvailabilityWindow(day, start, end);
        }

        static WindowDto from(AvailabilityWindow w) {
            return new WindowDto(w.day(), w.start(), w.end());
        }
    }

    public record AddMaidRequest(@NotBlank String name, @NotBlank String locality, @NotNull Gender gender,
                                 @DecimalMin("0") @DecimalMax("5") double rating,
                                 @NotEmpty Map<ServiceType, BigDecimal> hourlyRates, Set<String> skills,
                                 @NotEmpty List<@Valid WindowDto> availability) {
    }

    public record MaidResponse(String id, String name, String locality, Gender gender, double rating,
                               Map<ServiceType, BigDecimal> hourlyRates, Set<String> skills,
                               List<WindowDto> availability) {
        static MaidResponse from(Maid m) {
            return new MaidResponse(m.getId(), m.getName(), m.getLocality(), m.getGender(), m.getRating(),
                    m.getHourlyRates(), m.getSkills(), m.getAvailability().stream().map(WindowDto::from).toList());
        }
    }
}
