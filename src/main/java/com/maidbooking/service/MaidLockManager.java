package com.maidbooking.service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

// Serialises every mutation of a maid's inventory (book, pay, cancel) behind one lock per maid.
@Component
public class MaidLockManager {
    private final Map<String, ReentrantLock> locks = new ConcurrentHashMap<>();

    public <T> T withLock(String maidId, Supplier<T> action) {
        ReentrantLock lock = locks.computeIfAbsent(maidId, id -> new ReentrantLock());
        lock.lock();
        try {
            return action.get();
        } finally {
            lock.unlock();
        }
    }
}
