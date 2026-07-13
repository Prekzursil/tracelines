# Explain it like I'm 5

Imagine a little car with a camera on its roof. It drives down real streets and takes pictures
the whole way, so that later you can go on the internet and "stand" on that street and look around.
That's **Street View**.

Now, some streets have been driven by the camera car, and some haven't. **tracelines finds all the
streets that the car actually drove** and draws them as **blue lines** on a map.

## But what about the blue dots?

Sometimes a person visits a cool place, takes one 360° photo with their phone, and uploads it.
Those show up as little **blue dots** (they're called *photospheres*). They're nice, but they're
**not** the camera car — they're just one person's one photo.

**tracelines only keeps the blue lines (the car), never the blue dots (the phone photos).** That's
the one big rule, and we never break it.

## So what do I get?

A file (called **GeoJSON**) that lists every street the car drove. You can:

- open it on a map and look at it,
- see *when* each street was last driven,
- compare different camera companies (Google, Mapillary, KartaView).

## Want to try it?

The quickest thing: open the **[live map](https://prekzursil.github.io/tracelines/)** and press
**"Full Bucharest"** — you'll see every street the car drove in a whole city, in blue.

Ready for real words? → **[Street View coverage in plain English (101)](concepts.md)**
