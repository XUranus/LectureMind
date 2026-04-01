## Build The Slides

For speaker *AAAA*, *BBBB*, *CCCC*:

```bash
# substitude speaker placeholder
sed 's/Speaker_A/AAAA/g; s/Speaker_B/BBBB/g; s/Speaker_C/CCCC/g' slides.md > slides.final.md

# build pptx file
marp slides.final.md --pptx
```%             