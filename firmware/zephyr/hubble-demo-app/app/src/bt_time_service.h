/*
 * Copyright (c) 2025 Hubble Network, Inc.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/kernel.h>


/**
 * @brief BLE service for time sync.
 *
 * This function advertises Hubble UUID and waits (synchronously)
 * for a connection with Hubble Connect APP to sync time.
 *
 * @param timeout The amount of time to wait for time synchronization.
 * @return UTC time  on success or (negative) error code otherwise.
 */
int64_t bt_time_sync(k_timeout_t timeout);
