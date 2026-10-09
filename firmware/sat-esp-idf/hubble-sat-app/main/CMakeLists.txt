# Copyright (c) 2026 Hubble Network, Inc.
# SPDX-License-Identifier: Apache-2.0

set(SOURCES "main.c")

idf_component_register(SRCS ${SOURCES}
		       PRIV_REQUIRES bt nvs_flash
		       INCLUDE_DIRS ".")
