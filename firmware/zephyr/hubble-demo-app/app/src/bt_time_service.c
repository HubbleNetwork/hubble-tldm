/*
 * Copyright (c) 2025 Hubble Network, Inc.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>

#define HUBBLE_BLE_UUID_CONNECTABLE 0xFCA7

/* Time sync protocol */
#define PKT_CMD              0x02
#define PKT_CMD_SETUTC       0x02
#define PKT_CMD_SETEPHEMERIS 0x07

#define TIME_SYNC_SVC_UUID         \
	BT_UUID_128_ENCODE(0xef2dc9a1, 0x40be, 0x44b6, 0x9dda, 0x8a00fcd61dc0)
#define TIME_SYNC_CHR_UUID         \
	BT_UUID_128_ENCODE(0xef2dc9a1, 0x40be, 0x44b6, 0x9dda, 0x8a00fcd61dc1)

static struct bt_data connect_ad[] = {
	BT_DATA_BYTES(BT_DATA_UUID16_ALL,
		      BT_UUID_16_ENCODE(HUBBLE_BLE_UUID_CONNECTABLE)),
	BT_DATA_BYTES(BT_DATA_SVC_DATA16,
		      BT_UUID_16_ENCODE(HUBBLE_BLE_UUID_CONNECTABLE)),
};

K_SEM_DEFINE(init_sem, 0, 1);

static uint64_t current_time;

static const struct bt_uuid_128 time_sync_svc_uuid = BT_UUID_INIT_128(TIME_SYNC_SVC_UUID);
static const struct bt_uuid_128 time_sync_chr_uuid = BT_UUID_INIT_128(TIME_SYNC_CHR_UUID);

static void _adv_provisioning_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	(void)bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_USE_NRPA | BT_LE_ADV_OPT_CONN,
					       BT_GAP_ADV_FAST_INT_MIN_2,
					       BT_GAP_ADV_FAST_INT_MAX_2, NULL),
			       connect_ad, ARRAY_SIZE(connect_ad), NULL, 0);
}

int64_t bt_time_sync(k_timeout_t timeout)
{
	int ret;

	ret = bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_USE_NRPA | BT_LE_ADV_OPT_CONN,
					       BT_GAP_ADV_FAST_INT_MIN_2,
					       BT_GAP_ADV_FAST_INT_MAX_2, NULL),
			      connect_ad, ARRAY_SIZE(connect_ad), NULL, 0);
	if (ret != 0) {
		return ret;
	}

	ret = k_sem_take(&init_sem, timeout);

	bt_le_adv_stop();

	return ret != 0 ? ret : (int64_t)current_time;
}

K_WORK_DEFINE(provisioning_work, _adv_provisioning_work_handler);

static ssize_t _time_sync_chr_write_cb(struct bt_conn *conn, const struct bt_gatt_attr *attr,
				      const void *data, uint16_t len, uint16_t offset, uint8_t flags)
{
	int ret = -EINVAL;

	if (((uint8_t *)data)[0] != PKT_CMD) {
		return -ENOENT;
	}

	switch (((uint8_t *)data)[1]) {
	case PKT_CMD_SETUTC:
		if (len != (2 + sizeof(uint64_t))) {
			break;
		}
		memcpy(&current_time, &((uint8_t *)data)[2], sizeof(current_time));
		ret = len;
	case PKT_CMD_SETEPHEMERIS:
		/* Needed by Hubble Connect APP */
		ret = len;
		break;
	default:
		break;
	}

	return ret;
}

static void _disconnected_cb(struct bt_conn *conn, uint8_t reason)
{
	ARG_UNUSED(conn);
	ARG_UNUSED(reason);

	if (current_time != 0) {
		k_sem_give(&init_sem);
	} else {
		k_work_submit(&provisioning_work);
	}
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.disconnected = _disconnected_cb,
};

/* Check for BT_GATT_PERM_WRITE_LESC permissions */
BT_GATT_SERVICE_DEFINE(vnd_svc,
	BT_GATT_PRIMARY_SERVICE(&time_sync_svc_uuid),
	BT_GATT_CHARACTERISTIC(&time_sync_chr_uuid.uuid,
			       BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
			       BT_GATT_PERM_WRITE,
			       NULL, _time_sync_chr_write_cb, NULL),
		      );
