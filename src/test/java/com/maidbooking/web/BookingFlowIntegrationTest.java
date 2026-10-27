package com.maidbooking.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BookingFlowIntegrationTest {
    @Autowired
    private MockMvc mvc;
    @Autowired
    private ObjectMapper json;

    private static final String MAID = """
            {"name":"Asha","locality":"Koramangala","gender":"FEMALE","rating":4.5,
             "hourlyRates":{"CLEANING":200},"skills":["deep-cleaning"],
             "availability":[%s]}""".formatted(allDays());

    private static String allDays() {
        String[] days = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"};
        StringBuilder sb = new StringBuilder();
        for (String d : days) {
            if (sb.length() > 0) sb.append(',');
            sb.append("{\"day\":\"%s\",\"start\":\"08:00\",\"end\":\"20:00\"}".formatted(d));
        }
        return sb.toString();
    }

    private JsonNode send(org.springframework.test.web.servlet.RequestBuilder request, int expectedStatus) throws Exception {
        String body = mvc.perform(request).andExpect(status().is(expectedStatus)).andReturn().getResponse().getContentAsString();
        return body.isEmpty() ? null : json.readTree(body);
    }

    @Test
    void discoverBookPayCancelEndToEnd() throws Exception {
        String maidId = send(post("/api/maids").contentType(MediaType.APPLICATION_JSON).content(MAID), 201).get("id").asText();
        LocalDateTime start = LocalDateTime.now().plusDays(3).withHour(10).truncatedTo(ChronoUnit.HOURS);

        mvc.perform(get("/api/maids/search").param("locality", "koramangala").param("serviceType", "CLEANING")
                        .param("date", start.toLocalDate().toString()).param("startTime", "10:00"))
                .andExpect(status().isOk()).andExpect(jsonPath("$[0].id").value(maidId));

        String bookingBody = """
                {"customerId":"c1","maidId":"%s","serviceType":"CLEANING","bookingType":"SCHEDULED",
                 "durationMinutes":60,"startDateTime":"%s"}""".formatted(maidId, start);
        JsonNode booking = send(post("/api/bookings").contentType(MediaType.APPLICATION_JSON).content(bookingBody), 201);
        String bookingId = booking.get("id").asText();

        send(post("/api/bookings").contentType(MediaType.APPLICATION_JSON).content(bookingBody), 409);

        mvc.perform(get("/api/maids/search").param("locality", "koramangala")
                        .param("date", start.toLocalDate().toString()).param("startTime", "10:00"))
                .andExpect(jsonPath("$").isEmpty());

        send(post("/api/bookings/" + bookingId + "/payments").header("Idempotency-Key", "k1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"method\":\"UPI\",\"instrument\":\"asha@upi\"}"), 201);

        mvc.perform(post("/api/bookings/" + bookingId + "/cancel"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalRefund").value(200.0))
                .andExpect(jsonPath("$.booking.status").value("CANCELLED"));

        mvc.perform(get("/api/maids/search").param("locality", "koramangala")
                        .param("date", start.toLocalDate().toString()).param("startTime", "10:00"))
                .andExpect(jsonPath("$[0].id").value(maidId));
    }

    @Test
    void invalidRequestsReturn400And404() throws Exception {
        mvc.perform(post("/api/maids").contentType(MediaType.APPLICATION_JSON).content("{}")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/bookings/nope")).andExpect(status().isNotFound());
        mvc.perform(get("/api/maids/search").param("date", "2030-01-01")).andExpect(status().isBadRequest());
    }
}
