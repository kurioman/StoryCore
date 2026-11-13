set -e
cd /root/decomp && rm -rf out && mkdir -p out/i18n/locales && node split.mjs app.cut.jsx out | tail -1
cd out && npx -y prettier@3 --print-width 120 --write "**/*.{js,jsx}" > /dev/null 2>&1
cd /root/sc/app/frontend/src && rm -rf app features lib components/ui.jsx && cp -r /root/decomp/out/app /root/decomp/out/features /root/decomp/out/lib . && cp /root/decomp/out/components/ui.jsx components/ && cp /root/decomp/out/i18n/locales/en.extracted.json i18n/locales/en.json
