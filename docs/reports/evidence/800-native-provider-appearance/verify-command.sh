#!/bin/bash
set -euo pipefail
: "${SIMULATOR_ID:?Set an isolated simulator UUID}"
TEST_RUNNER_ARGUS_TEST_NATIVE_PROVIDER_APPEARANCE=true \
TEST_RUNNER_ARGUS_TEST_AUTH_UI_ENABLED=true \
TEST_RUNNER_ARGUS_TEST_EXPECT_APPLE=true \
TEST_RUNNER_ARGUS_TEST_EXPECT_GOOGLE=true \
ios/scripts/verify.sh test \
  -only-testing:ArgusFoundationUITests/NativeProviderAppearanceUITests \
  -only-testing:ArgusFoundationUITests/CuadraoSignInPresentationUITests \
  ARGUS_AUTH_ENABLED=true \
  ARGUS_API_URL=http://127.0.0.1:9 \
  ARGUS_SUPABASE_URL=http://127.0.0.1:9 \
  ARGUS_SUPABASE_ANON_KEY=sb_publishable_appearance_placeholder \
  ARGUS_WEB_URL=http://127.0.0.1:9 \
  ARGUS_CAPTCHA_URL=http://127.0.0.1:9/captcha \
  ARGUS_APPLE_SIGN_IN_ENABLED=true ARGUS_GOOGLE_SIGN_IN_ENABLED=true \
  GOOGLE_SIGN_IN_IOS_CLIENT_ID=123-appearance.apps.googleusercontent.com \
  GOOGLE_SIGN_IN_IOS_URL_SCHEME=com.googleusercontent.apps.123-appearance
